import type { ProfileImportProvider, ProfileImportUploadItem } from "./personalization-api";

export interface DirectorySourceFile<TFile = File> {
  name: string;
  size: number;
  webkitRelativePath?: string;
  file: TFile;
}

export interface ProviderFolderSelection<TFile = File> {
  rootName: string;
  files: ProviderCandidateFile<TFile>[];
  groups: ProviderCandidateGroup<TFile>[];
  totalBytes: number;
  totalFileCount: number;
  filteredBytes: number;
}

export interface ProviderCandidateFile<TFile = File> {
  id: string;
  file: TFile;
  relative_path: string;
  size: number;
  group_id: string;
  file_label: string;
}

export interface ProviderCandidateGroup<TFile = File> {
  id: string;
  label: string;
  hint?: string;
  files: ProviderCandidateFile<TFile>[];
  totalBytes: number;
}

type TextReadableFile = {
  text?: () => Promise<string>;
  slice?: (start?: number, end?: number) => { text?: () => Promise<string> };
};

interface ProviderGroupingContext {
  cursorWorkspacePaths?: Map<string, string>;
}

function normalizePath(value: string): string {
  return value.replaceAll("\\", "/").replace(/^\/+/, "");
}

function basename(value: string): string {
  const normalized = normalizePath(value);
  const parts = normalized.split("/");
  return parts[parts.length - 1] || "";
}

function dirname(value: string): string {
  const normalized = normalizePath(value);
  const parts = normalized.split("/");
  parts.pop();
  return parts.join("/");
}

function decodeClaudeProjectPath(segment: string): string {
  if (!segment.startsWith("-")) {
    return segment;
  }
  const parts = segment.split("-").filter(Boolean);
  if (parts.length >= 3 && (parts[0] === "Users" || parts[0] === "home")) {
    return `~/${parts.slice(2).join("/")}`;
  }
  if (parts.length === 0) {
    return segment;
  }
  return `/${parts.join("/")}`;
}

function humanizeAbsolutePath(value: string): string {
  const normalized = value.replaceAll("\\", "/").replace(/\/+$/, "");
  const macMatch = normalized.match(/^\/Users\/[^/]+\/?(.*)$/);
  if (macMatch) {
    return macMatch[1] ? `~/${macMatch[1]}` : "~";
  }
  const linuxMatch = normalized.match(/^\/home\/[^/]+\/?(.*)$/);
  if (linuxMatch) {
    return linuxMatch[1] ? `~/${linuxMatch[1]}` : "~";
  }
  return normalized;
}

function labelFromDisplayPath(value: string): string {
  const normalized = value.replace(/\/+$/, "");
  return basename(normalized) || normalized;
}

function decodeFileUri(value: string): string | null {
  if (!value.startsWith("file://")) {
    return null;
  }
  const withoutScheme = value.slice("file://".length);
  try {
    return decodeURIComponent(withoutScheme);
  } catch {
    return withoutScheme;
  }
}

function buildFallbackGroupDescriptor(
  provider: ProfileImportProvider,
  relativePath: string,
  context?: ProviderGroupingContext,
): { groupId: string; groupLabel: string; groupHint?: string; fileLabel: string } {
  const normalized = normalizePath(relativePath);
  const fileLabel = basename(normalized);
  const segments = normalized.split("/");

  if (provider === "claude_code") {
    const projectSegment = segments[1] || "unknown-project";
    const displayPath = decodeClaudeProjectPath(projectSegment);
    return {
      groupId: `claude:${projectSegment}`,
      groupLabel: labelFromDisplayPath(displayPath),
      groupHint: displayPath,
      fileLabel,
    };
  }

  if (provider === "cursor") {
    if (normalized.startsWith("globalStorage/")) {
      return {
        groupId: "cursor:globalStorage",
        groupLabel: "Global Storage",
        groupHint: "globalStorage",
        fileLabel,
      };
    }
    const workspaceId = segments[1] || "unknown-workspace";
    const workspacePath = context?.cursorWorkspacePaths?.get(workspaceId);
    if (workspacePath) {
      const displayPath = humanizeAbsolutePath(workspacePath);
      return {
        groupId: `cursor:${workspaceId}`,
        groupLabel: labelFromDisplayPath(displayPath),
        groupHint: displayPath,
        fileLabel,
      };
    }
    return {
      groupId: `cursor:${workspaceId}`,
      groupLabel: `Workspace ${workspaceId}`,
      groupHint: `workspaceStorage/${workspaceId}`,
      fileLabel,
    };
  }

  const parentPath = dirname(normalized);
  const [bucket, ...rest] = parentPath.split("/");
  return {
    groupId: `codex:${parentPath}`,
    groupLabel: rest.length > 0 ? `${bucket} / ${rest.join("/")}` : parentPath || "sessions",
    groupHint: parentPath,
    fileLabel,
  };
}

async function readFilePreviewText(file: unknown): Promise<string> {
  if (!file || typeof file !== "object") {
    return "";
  }
  const readable = file as TextReadableFile;
  const sliced = readable.slice?.(0, 16 * 1024);
  if (sliced?.text) {
    try {
      return await sliced.text();
    } catch {
      // fall through to full text
    }
  }
  if (readable.text) {
    try {
      return await readable.text();
    } catch {
      return "";
    }
  }
  return "";
}

function findPathCandidate(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  if (!trimmed.startsWith("/")) {
    return null;
  }
  return trimmed;
}

function extractCodexProjectPathFromPreview(rawText: string): string | null {
  for (const line of rawText.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const record = JSON.parse(trimmed) as Record<string, unknown>;
      const directCandidates = [
        findPathCandidate(record.cwd),
        findPathCandidate(record.project_path),
        findPathCandidate(record.projectPath),
      ];
      for (const candidate of directCandidates) {
        if (candidate) return candidate;
      }
      const payload =
        record.payload && typeof record.payload === "object"
          ? (record.payload as Record<string, unknown>)
          : null;
      if (!payload) continue;
      const payloadCandidates = [
        findPathCandidate(payload.cwd),
        findPathCandidate(payload.project_path),
        findPathCandidate(payload.projectPath),
      ];
      for (const candidate of payloadCandidates) {
        if (candidate) return candidate;
      }
    } catch {
      continue;
    }
  }
  return null;
}

async function buildGroupDescriptor<TFile>(
  provider: ProfileImportProvider,
  item: { file: TFile; relative_path: string },
  context?: ProviderGroupingContext,
): Promise<{ groupId: string; groupLabel: string; groupHint?: string; fileLabel: string }> {
  const fallback = buildFallbackGroupDescriptor(provider, item.relative_path, context);
  if (provider !== "codex") {
    return fallback;
  }
  const previewText = await readFilePreviewText(item.file);
  const projectPath = extractCodexProjectPathFromPreview(previewText);
  if (!projectPath) {
    return fallback;
  }
  const displayPath = humanizeAbsolutePath(projectPath);
  return {
    groupId: `codex-project:${projectPath}`,
    groupLabel: labelFromDisplayPath(displayPath),
    groupHint: displayPath,
    fileLabel: fallback.fileLabel,
  };
}

async function buildProviderGroupingContext<TFile>(
  provider: ProfileImportProvider,
  rawFiles: Array<DirectorySourceFile<TFile>>,
  commonRoot: string,
): Promise<ProviderGroupingContext> {
  if (provider !== "cursor") {
    return {};
  }
  const workspacePaths = new Map<string, string>();
  for (const rawFile of rawFiles) {
    const originalPath = normalizePath(rawFile.webkitRelativePath || rawFile.name);
    const relativePath =
      commonRoot && originalPath.startsWith(`${commonRoot}/`)
        ? originalPath.slice(commonRoot.length + 1)
        : originalPath;
    const normalized = normalizePath(relativePath);
    const match = normalized.match(/^workspaceStorage\/([^/]+)\/workspace\.json$/);
    if (!match) {
      continue;
    }
    const rawText = await readFilePreviewText(rawFile.file);
    if (!rawText) {
      continue;
    }
    try {
      const payload = JSON.parse(rawText) as Record<string, unknown>;
      const folderValue =
        typeof payload.folder === "string"
          ? payload.folder
          : typeof payload.workspace === "string"
            ? payload.workspace
            : null;
      const decodedFolder = folderValue ? decodeFileUri(folderValue) ?? folderValue : null;
      const candidate = decodedFolder && findPathCandidate(decodedFolder);
      if (candidate) {
        workspacePaths.set(match[1], candidate);
      }
    } catch {
      continue;
    }
  }
  return { cursorWorkspacePaths: workspacePaths };
}

function compareProviderGroups(
  provider: ProfileImportProvider,
  left: ProviderCandidateGroup<unknown>,
  right: ProviderCandidateGroup<unknown>,
): number {
  if (provider === "codex") {
    const codexWeight = (value: string): number => {
      if (value.startsWith("sessions/")) return 1;
      if (value.startsWith("archived_sessions/")) return 2;
      return 0;
    };
    const byWeight = codexWeight(left.hint || left.label) - codexWeight(right.hint || right.label);
    if (byWeight !== 0) {
      return byWeight;
    }
  }
  return left.label.localeCompare(right.label);
}

export function shouldIncludeProviderHistoryFile(
  provider: ProfileImportProvider,
  relativePath: string,
): boolean {
  const normalized = normalizePath(relativePath);
  const name = basename(normalized);

  if (provider === "codex") {
    const inCodexSessions =
      normalized.startsWith("sessions/") || normalized.startsWith("archived_sessions/");
    return inCodexSessions && /^rollout-.*\.jsonl$/i.test(name);
  }

  if (provider === "claude_code") {
    return normalized.startsWith("projects/") && normalized.endsWith(".jsonl");
  }

  if (provider === "cursor") {
    if (
      normalized === "globalStorage/state.vscdb" ||
      normalized === "globalStorage/state.vscdb-wal" ||
      normalized === "globalStorage/state.vscdb-shm"
    ) {
      return true;
    }
    return (
      normalized.startsWith("workspaceStorage/") &&
      /\/state\.vscdb(?:-wal|-shm)?$/i.test(normalized)
    );
  }

  return false;
}

export async function buildProviderFolderSelection<TFile = File>(
  provider: ProfileImportProvider,
  sourceFiles: Iterable<DirectorySourceFile<TFile>>,
): Promise<ProviderFolderSelection<TFile>> {
  const rawFiles = Array.from(sourceFiles);
  const rawPaths = rawFiles
    .map((file) => normalizePath(file.webkitRelativePath || file.name))
    .filter(Boolean);
  const firstSegments = rawPaths.map((path) => path.split("/")[0] || "");
  const commonRoot =
    rawPaths.length > 0 &&
    rawPaths.every((path) => path.includes("/")) &&
    firstSegments.every((item) => item === firstSegments[0])
      ? firstSegments[0]!
      : "";
  const context = await buildProviderGroupingContext(provider, rawFiles, commonRoot);

  const filteredFiles = rawFiles
    .map((file) => {
      const originalPath = normalizePath(file.webkitRelativePath || file.name);
      const relativePath =
        commonRoot && originalPath.startsWith(`${commonRoot}/`)
          ? originalPath.slice(commonRoot.length + 1)
          : originalPath;
      return {
        file: file.file,
        relative_path: relativePath || file.name,
        size: file.size,
      };
    })
    .filter((item) => shouldIncludeProviderHistoryFile(provider, item.relative_path));

  const files = await Promise.all(
    filteredFiles.map(async (item) => {
      const descriptor = await buildGroupDescriptor(provider, item, context);
      return {
        id: item.relative_path,
        file: item.file,
        relative_path: item.relative_path,
        size: item.size,
        group_id: descriptor.groupId,
        file_label: descriptor.fileLabel,
        group_label: descriptor.groupLabel,
        group_hint: descriptor.groupHint,
      };
    }),
  );

  const groupsById = new Map<string, ProviderCandidateGroup<TFile>>();
  for (const file of files) {
    const current = groupsById.get(file.group_id);
    if (current) {
      current.files.push(file);
      current.totalBytes += file.size;
      continue;
    }
    groupsById.set(file.group_id, {
      id: file.group_id,
      label: file.group_label,
      hint: file.group_hint,
      files: [file],
      totalBytes: file.size,
    });
  }

  const groups = Array.from(groupsById.values()).sort((left, right) =>
    compareProviderGroups(provider, left, right),
  );
  for (const group of groups) {
    group.files.sort((left, right) => left.relative_path.localeCompare(right.relative_path));
  }

  return {
    rootName: commonRoot || rawFiles[0]?.name || "",
    files,
    groups,
    totalBytes: rawFiles.reduce((sum, file) => sum + file.size, 0),
    totalFileCount: rawFiles.length,
    filteredBytes: files.reduce((sum, file) => sum + file.size, 0),
  };
}

export async function buildUploadItemsFromFileList(
  provider: ProfileImportProvider,
  fileList: FileList,
): Promise<ProviderFolderSelection<File>> {
  const sourceFiles = Array.from(fileList).map((file) => ({
    name: file.name,
    size: file.size,
    webkitRelativePath: (file as File & { webkitRelativePath?: string }).webkitRelativePath,
    file,
  }));
  return buildProviderFolderSelection(provider, sourceFiles);
}

export function toProfileImportUploadItems(
  files: ReadonlyArray<Pick<ProviderCandidateFile<File>, "file" | "relative_path">>,
): ProfileImportUploadItem[] {
  return files.map((item) => ({
    file: item.file,
    relative_path: item.relative_path,
  }));
}
