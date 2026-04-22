"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  FileUp,
  FolderOpen,
  Loader2,
  Sparkles,
  Type,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import Modal from "@/components/common/Modal";
import {
  applyProfileImport,
  applyProfileImportUpload,
  previewProfileImport,
  previewProfileImportUpload,
  type ProfileImportApplyResponse,
  type ProfileImportMode,
  type ProfileImportPreviewResponse,
  type ProfileImportProvider,
  type ProfileImportSourceType,
} from "@/lib/personalization-api";
import {
  buildUploadItemsFromFileList,
  toProfileImportUploadItems,
  type ProviderCandidateGroup,
  type ProviderFolderSelection,
} from "@/lib/profile-import-folder";

const MarkdownRenderer = dynamic(() => import("@/components/common/MarkdownRenderer"), {
  ssr: false,
});

interface ProfileImportModalProps {
  isOpen: boolean;
  language: string;
  onClose: () => void;
  onApplied: (result: ProfileImportApplyResponse) => Promise<void> | void;
}

const MODE_OPTIONS: { value: ProfileImportMode }[] = [
  { value: "merge" },
  { value: "create" },
  { value: "overwrite" },
];

const SOURCE_OPTIONS: { value: ProfileImportSourceType; icon: typeof FolderOpen }[] = [
  { value: "folder", icon: FolderOpen },
  { value: "pasted_text", icon: Type },
];

const PROVIDER_OPTIONS: ProfileImportProvider[] = ["codex", "claude_code", "cursor"];

type DirectoryInput = HTMLInputElement & {
  webkitdirectory?: boolean;
  directory?: boolean;
};

interface SelectedFolderState extends ProviderFolderSelection<File> {}

const EMPTY_FOLDER_SELECTION: SelectedFolderState = {
  rootName: "",
  files: [],
  groups: [],
  totalBytes: 0,
  totalFileCount: 0,
  filteredBytes: 0,
};

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ProfileImportModal({
  isOpen,
  language,
  onClose,
  onApplied,
}: ProfileImportModalProps) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<ProfileImportMode>("merge");
  const [sourceType, setSourceType] = useState<ProfileImportSourceType>("folder");
  const [provider, setProvider] = useState<ProfileImportProvider>("codex");
  const [folderSelection, setFolderSelection] = useState<SelectedFolderState>(EMPTY_FOLDER_SELECTION);
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([]);
  const [expandedGroupIds, setExpandedGroupIds] = useState<string[]>([]);
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<ProfileImportPreviewResponse | null>(null);
  const [scanning, setScanning] = useState(false);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!isOpen) {
      setMode("merge");
      setSourceType("folder");
      setProvider("codex");
      setFolderSelection(EMPTY_FOLDER_SELECTION);
      setSelectedFileIds([]);
      setExpandedGroupIds([]);
      setText("");
      setPreview(null);
      setScanning(false);
      setError("");
    }
  }, [isOpen]);

  const bindDirectoryInput = useCallback((node: HTMLInputElement | null) => {
    inputRef.current = node;
    if (!node) return;
    const directoryNode = node as DirectoryInput;
    directoryNode.webkitdirectory = true;
    directoryNode.directory = true;
    node.setAttribute("webkitdirectory", "true");
    node.setAttribute("directory", "true");
  }, []);

  const selectedFileSet = useMemo(() => new Set(selectedFileIds), [selectedFileIds]);

  const selectedFiles = useMemo(
    () => folderSelection.files.filter((file) => selectedFileSet.has(file.id)),
    [folderSelection.files, selectedFileSet],
  );

  const selectedBytes = useMemo(
    () => selectedFiles.reduce((sum, file) => sum + file.size, 0),
    [selectedFiles],
  );

  const canPreview = useMemo(() => {
    if (scanning || loading || applying) return false;
    if (sourceType === "folder") return selectedFiles.length > 0;
    return text.trim().length > 0;
  }, [applying, loading, scanning, selectedFiles.length, sourceType, text]);

  const resetFolderState = useCallback(() => {
    setFolderSelection(EMPTY_FOLDER_SELECTION);
    setSelectedFileIds([]);
    setExpandedGroupIds([]);
  }, []);

  const handleFolderPick = () => {
    inputRef.current?.click();
  };

  const handleFolderSelected = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = event.target.files;
    if (!fileList || fileList.length === 0) return;
    setScanning(true);
    try {
      const selection = await buildUploadItemsFromFileList(provider, fileList);
      setFolderSelection(selection);
      setSelectedFileIds(selection.files.map((file) => file.id));
      setExpandedGroupIds(selection.groups.map((group) => group.id));
      setPreview(null);
      setError(selection.files.length > 0 ? "" : t("profile_import.modal.folder_no_match"));
    } finally {
      setScanning(false);
    }
    event.target.value = "";
  };

  const handleToggleFile = useCallback((fileId: string) => {
    setSelectedFileIds((current) =>
      current.includes(fileId)
        ? current.filter((item) => item !== fileId)
        : [...current, fileId],
    );
    setPreview(null);
    setError("");
  }, []);

  const handleToggleGroup = useCallback((group: ProviderCandidateGroup<File>) => {
    const groupIds = group.files.map((file) => file.id);
    setSelectedFileIds((current) => {
      const currentSet = new Set(current);
      const everySelected = groupIds.every((id) => currentSet.has(id));
      if (everySelected) {
        return current.filter((id) => !groupIds.includes(id));
      }
      for (const id of groupIds) {
        currentSet.add(id);
      }
      return folderSelection.files
        .map((file) => file.id)
        .filter((id) => currentSet.has(id));
    });
    setPreview(null);
    setError("");
  }, [folderSelection.files]);

  const handleToggleGroupExpanded = useCallback((groupId: string) => {
    setExpandedGroupIds((current) =>
      current.includes(groupId)
        ? current.filter((item) => item !== groupId)
        : [...current, groupId],
    );
  }, []);

  const handleSelectAll = useCallback(() => {
    setSelectedFileIds(folderSelection.files.map((file) => file.id));
    setPreview(null);
    setError("");
  }, [folderSelection.files]);

  const handleClearSelection = useCallback(() => {
    setSelectedFileIds([]);
    setPreview(null);
    setError("");
  }, []);

  const handlePreview = async () => {
    if (!canPreview) return;
    if (sourceType === "folder" && selectedFiles.length === 0) {
      setError(t("profile_import.modal.folder_none_selected"));
      return;
    }
    setLoading(true);
    setError("");
    try {
      const result =
        sourceType === "folder"
          ? await previewProfileImportUpload({
              mode,
              language,
              provider,
              files: toProfileImportUploadItems(selectedFiles),
            })
          : await previewProfileImport({
              mode,
              language,
              source_type: sourceType,
              provider: null,
              folder_path: null,
              text,
            });
      setPreview(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Unknown error"));
    } finally {
      setLoading(false);
    }
  };

  const handleApply = async () => {
    if (!preview?.can_apply || applying) return;
    if (sourceType === "folder" && selectedFiles.length === 0) {
      setError(t("profile_import.modal.folder_none_selected"));
      return;
    }
    setApplying(true);
    setError("");
    try {
      const result =
        sourceType === "folder"
          ? await applyProfileImportUpload({
              mode,
              language,
              provider,
              files: toProfileImportUploadItems(selectedFiles),
            })
          : await applyProfileImport({
              mode,
              language,
              source_type: sourceType,
              provider: null,
              folder_path: null,
              text,
            });
      await onApplied(result);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Unknown error"));
    } finally {
      setApplying(false);
    }
  };

  const footer = (
    <div className="flex items-center justify-between gap-3">
      <div className="text-[12px] text-[var(--muted-foreground)]">
        {t("profile_import.modal.footer_notice")}
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onClose}
          disabled={scanning || loading || applying}
          className="rounded-lg border border-[var(--border)]/70 px-3 py-2 text-[13px] text-[var(--muted-foreground)] transition-colors hover:border-[var(--border)] hover:text-[var(--foreground)] disabled:opacity-50"
        >
          {t("profile_import.modal.cancel")}
        </button>
        <button
          type="button"
          onClick={() => void handlePreview()}
          disabled={!canPreview}
          className="rounded-lg border border-[var(--border)]/70 px-3 py-2 text-[13px] font-medium text-[var(--foreground)] transition-colors hover:border-[var(--border)] disabled:opacity-40"
        >
          {loading ? t("profile_import.modal.previewing") : t("profile_import.modal.preview")}
        </button>
        <button
          type="button"
          onClick={() => void handleApply()}
          disabled={!preview?.can_apply || applying}
          className="inline-flex items-center gap-2 rounded-lg bg-[var(--foreground)] px-3 py-2 text-[13px] font-medium text-[var(--background)] transition-opacity disabled:opacity-40"
        >
          {applying ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          {t("profile_import.modal.apply")}
        </button>
      </div>
    </div>
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={scanning || loading || applying ? () => undefined : onClose}
      title={t("profile_import.modal.title")}
      titleIcon={<FileUp className="h-4 w-4" />}
      width="xl"
      footer={footer}
      closeOnBackdrop={!scanning && !loading && !applying}
    >
      <div className="space-y-5 px-5 py-4">
        <input
          ref={bindDirectoryInput}
          type="file"
          multiple
          className="hidden"
          onChange={handleFolderSelected}
        />

        <div className="rounded-2xl border border-[var(--border)]/70 bg-[linear-gradient(135deg,rgba(255,255,255,0.92),rgba(236,231,221,0.72))] p-4">
          <p className="text-[11px] uppercase tracking-[0.24em] text-[var(--primary)]">{t("profile_import.modal.kicker")}</p>
          <p className="mt-2 max-w-2xl text-[13px] leading-6 text-[var(--muted-foreground)]">
            {t("profile_import.modal.subtitle")}
          </p>
        </div>

        <div>
          <p className="mb-2 text-[12px] font-medium text-[var(--foreground)]">{t("profile_import.modal.mode_label")}</p>
          <div className="grid gap-2 md:grid-cols-3">
            {MODE_OPTIONS.map((option) => {
              const active = option.value === mode;
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setMode(option.value)}
                  className={`rounded-xl border px-3 py-3 text-left transition-colors ${
                    active
                      ? "border-[var(--foreground)] bg-[var(--foreground)] text-[var(--background)]"
                      : "border-[var(--border)]/70 bg-[var(--card)] text-[var(--foreground)]"
                  }`}
                >
                  <div className="text-[13px] font-medium">{t(`profile_import.mode.${option.value}.label`)}</div>
                  <div className={`mt-1 text-[11px] ${active ? "text-[var(--background)]/75" : "text-[var(--muted-foreground)]"}`}>
                    {t(`profile_import.mode.${option.value}.hint`)}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <p className="mb-2 text-[12px] font-medium text-[var(--foreground)]">{t("profile_import.modal.source_label")}</p>
          <div className="grid gap-2 md:grid-cols-2">
            {SOURCE_OPTIONS.map((option) => {
              const active = option.value === sourceType;
              const Icon = option.icon;
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => {
                    setSourceType(option.value);
                    setPreview(null);
                    setError("");
                  }}
                  className={`rounded-xl border px-3 py-3 text-left transition-colors ${
                    active
                      ? "border-[var(--foreground)] bg-[var(--foreground)] text-[var(--background)]"
                      : "border-[var(--border)]/70 bg-[var(--card)] text-[var(--foreground)]"
                  }`}
                >
                  <div className="flex items-center gap-2 text-[13px] font-medium">
                    <Icon className="h-4 w-4" />
                    {t(`profile_import.source.${option.value}.label`)}
                  </div>
                  <div className={`mt-1 text-[11px] ${active ? "text-[var(--background)]/75" : "text-[var(--muted-foreground)]"}`}>
                    {t(`profile_import.source.${option.value}.hint`)}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {sourceType === "folder" ? (
          <div className="space-y-4">
            <div className="grid gap-4 md:grid-cols-[220px_minmax(0,1fr)]">
              <div className="space-y-2 rounded-2xl border border-[var(--border)]/70 bg-[var(--card)] p-4">
                <p className="text-[12px] font-medium text-[var(--foreground)]">{t("profile_import.modal.provider_label")}</p>
                {PROVIDER_OPTIONS.map((option) => {
                  const active = option === provider;
                  return (
                    <button
                      key={option}
                      type="button"
                      onClick={() => {
                        setProvider(option);
                        setPreview(null);
                        resetFolderState();
                        setError("");
                      }}
                      className={`w-full rounded-xl border px-3 py-2 text-left text-[13px] transition-colors ${
                        active
                          ? "border-[var(--foreground)] bg-[var(--foreground)] text-[var(--background)]"
                          : "border-[var(--border)]/70 bg-transparent text-[var(--foreground)]"
                      }`}
                    >
                      {t(`profile_import.provider.${option}`)}
                    </button>
                  );
                })}
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between gap-3">
                  <p className="text-[12px] font-medium text-[var(--foreground)]">{t("profile_import.modal.folder_label")}</p>
                  <span className="text-right text-[11px] text-[var(--muted-foreground)]">
                    {t(`profile_import.folder_hint.${provider}`)}
                  </span>
                </div>
                <div className="rounded-2xl border border-[var(--border)]/70 bg-[var(--card)] p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-[13px] font-medium text-[var(--foreground)]">
                        {folderSelection.rootName || t("profile_import.modal.folder_empty")}
                      </p>
                      <p className="mt-1 text-[11px] text-[var(--muted-foreground)]">
                        {folderSelection.files.length > 0
                          ? t("profile_import.modal.folder_stats", {
                              count: folderSelection.files.length,
                              size: formatBytes(folderSelection.filteredBytes),
                            })
                          : t("profile_import.modal.folder_help")}
                      </p>
                      {folderSelection.files.length > 0 &&
                      folderSelection.totalFileCount > folderSelection.files.length ? (
                        <p className="mt-1 text-[11px] text-[var(--muted-foreground)]/80">
                          {t("profile_import.modal.folder_filtered_stats", {
                            matched: folderSelection.files.length,
                            total: folderSelection.totalFileCount,
                            uploaded: formatBytes(folderSelection.filteredBytes),
                            original: formatBytes(folderSelection.totalBytes),
                          })}
                        </p>
                      ) : null}
                    </div>
                    <button
                      type="button"
                      onClick={handleFolderPick}
                      disabled={scanning}
                      className="inline-flex items-center gap-2 rounded-lg border border-[var(--border)]/70 px-3 py-2 text-[13px] font-medium text-[var(--foreground)] transition-colors hover:border-[var(--border)]"
                    >
                      <FolderOpen className="h-4 w-4" />
                      {folderSelection.files.length > 0
                        ? t("profile_import.modal.folder_replace")
                        : t("profile_import.modal.folder_choose")}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {folderSelection.files.length > 0 ? (
              <div className="rounded-2xl border border-[var(--border)]/70 bg-[var(--card)] p-4">
                <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--border)]/60 pb-3">
                  <div>
                    <p className="text-[12px] font-medium text-[var(--foreground)]">
                      {t("profile_import.modal.candidate_label")}
                    </p>
                    <p className="mt-1 text-[11px] text-[var(--muted-foreground)]">
                      {t("profile_import.modal.selection_stats", {
                        groups: folderSelection.groups.length,
                        matched: folderSelection.files.length,
                        selected: selectedFiles.length,
                        size: formatBytes(selectedBytes),
                      })}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={handleSelectAll}
                      className="rounded-lg border border-[var(--border)]/70 px-3 py-1.5 text-[12px] text-[var(--foreground)] transition-colors hover:border-[var(--border)]"
                    >
                      {t("profile_import.modal.select_all")}
                    </button>
                    <button
                      type="button"
                      onClick={handleClearSelection}
                      className="rounded-lg border border-[var(--border)]/70 px-3 py-1.5 text-[12px] text-[var(--muted-foreground)] transition-colors hover:border-[var(--border)] hover:text-[var(--foreground)]"
                    >
                      {t("profile_import.modal.clear_selection")}
                    </button>
                  </div>
                </div>

                <div className="mt-4 space-y-3">
                  {folderSelection.groups.map((group) => {
                    const selectedCount = group.files.filter((file) => selectedFileSet.has(file.id)).length;
                    const allSelected = selectedCount === group.files.length;
                    const partiallySelected = selectedCount > 0 && !allSelected;
                    const expanded = expandedGroupIds.includes(group.id);
                    return (
                      <div key={group.id} className="rounded-2xl border border-[var(--border)]/60 bg-[var(--background)]/70">
                        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                          <label className="flex min-w-0 flex-1 items-start gap-3">
                            <input
                              type="checkbox"
                              checked={allSelected}
                              ref={(node) => {
                                if (node) {
                                  node.indeterminate = partiallySelected;
                                }
                              }}
                              onChange={() => handleToggleGroup(group)}
                              className="mt-0.5 h-4 w-4 rounded border-[var(--border)] text-[var(--foreground)] accent-[var(--foreground)]"
                            />
                            <span className="min-w-0">
                              <span className="block truncate text-[13px] font-medium text-[var(--foreground)]">
                                {group.label}
                              </span>
                              <span className="mt-1 block text-[11px] text-[var(--muted-foreground)]">
                                {t("profile_import.modal.group_stats", {
                                  count: group.files.length,
                                  size: formatBytes(group.totalBytes),
                                  selected: selectedCount,
                                })}
                                {group.hint ? ` · ${group.hint}` : ""}
                              </span>
                            </span>
                          </label>
                          <button
                            type="button"
                            onClick={() => handleToggleGroupExpanded(group.id)}
                            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] text-[var(--muted-foreground)] transition-colors hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
                          >
                            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                            {expanded
                              ? t("profile_import.modal.collapse_group")
                              : t("profile_import.modal.expand_group")}
                          </button>
                        </div>

                        {expanded ? (
                          <div className="border-t border-[var(--border)]/50 px-4 py-3">
                            <div className="space-y-2">
                              {group.files.map((file) => (
                                <label
                                  key={file.id}
                                  className="flex items-start gap-3 rounded-xl border border-[var(--border)]/50 bg-[var(--card)]/70 px-3 py-2"
                                >
                                  <input
                                    type="checkbox"
                                    checked={selectedFileSet.has(file.id)}
                                    onChange={() => handleToggleFile(file.id)}
                                    className="mt-0.5 h-4 w-4 rounded border-[var(--border)] text-[var(--foreground)] accent-[var(--foreground)]"
                                  />
                                  <span className="min-w-0 flex-1">
                                    <span className="block truncate text-[12px] font-medium text-[var(--foreground)]">
                                      {file.file_label}
                                    </span>
                                    <span className="mt-1 block break-all font-mono text-[11px] text-[var(--muted-foreground)]">
                                      {file.relative_path}
                                    </span>
                                  </span>
                                  <span className="text-[11px] text-[var(--muted-foreground)]">
                                    {formatBytes(file.size)}
                                  </span>
                                </label>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : null}
          </div>
        ) : (
          <div>
            <div className="mb-2 flex items-center justify-between">
              <p className="text-[12px] font-medium text-[var(--foreground)]">{t("profile_import.modal.text_label")}</p>
              <span className="text-[11px] text-[var(--muted-foreground)]">{t("profile_import.modal.text_hint")}</span>
            </div>
            <textarea
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setPreview(null);
              }}
              spellCheck={false}
              className="min-h-[240px] w-full resize-none rounded-2xl border border-[var(--border)] bg-transparent px-4 py-3 font-mono text-[12px] leading-6 text-[var(--foreground)] outline-none transition-colors focus:border-[var(--ring)]"
              placeholder={t("profile_import.modal.placeholder")}
            />
          </div>
        )}

        {error ? (
          <div className="rounded-xl border border-red-500/30 bg-red-500/5 px-3 py-2 text-[12px] text-red-500">
            {error}
          </div>
        ) : null}

        {preview ? (
          <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
            <div className="space-y-3">
              <div className="rounded-2xl border border-[var(--border)]/70 bg-[var(--card)] p-4">
                <p className="text-[11px] uppercase tracking-[0.22em] text-[var(--muted-foreground)]">{t("profile_import.preview.stats")}</p>
                <div className="mt-3 space-y-2 text-[13px] text-[var(--foreground)]">
                  <div className="flex justify-between gap-3">
                    <span>{t("profile_import.preview.detected_turns")}</span>
                    <span>{preview.detected_turns}</span>
                  </div>
                  <div className="flex justify-between gap-3">
                    <span>{t("profile_import.preview.effective_signals")}</span>
                    <span>{preview.effective_signal_count}</span>
                  </div>
                  <div className="flex justify-between gap-3">
                    <span>{t("profile_import.preview.scanned_sessions")}</span>
                    <span>{preview.scanned_session_count}</span>
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-[var(--border)]/70 bg-[var(--card)] p-4">
                <p className="text-[11px] uppercase tracking-[0.22em] text-[var(--muted-foreground)]">{t("profile_import.preview.updated_sections")}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {preview.will_update_sections.map((section) => (
                    <span key={section} className="rounded-full bg-[var(--muted)] px-2.5 py-1 text-[11px] text-[var(--muted-foreground)]">
                      {section}
                    </span>
                  ))}
                </div>
              </div>

              <div className="rounded-2xl border border-[var(--border)]/70 bg-[var(--card)] p-4">
                <p className="text-[11px] uppercase tracking-[0.22em] text-[var(--muted-foreground)]">{t("profile_import.preview.signals")}</p>
                <div className="mt-3 space-y-2 text-[12px] leading-6 text-[var(--foreground)]">
                  {preview.extracted_user_messages.length > 0 ? (
                    preview.extracted_user_messages.map((item, index) => (
                      <div key={`${item}-${index}`} className="rounded-xl bg-[var(--muted)]/55 px-3 py-2">
                        {item}
                      </div>
                    ))
                  ) : (
                    <div className="text-[var(--muted-foreground)]">{t("profile_import.preview.no_signals")}</div>
                  )}
                </div>
              </div>

              {preview.warnings.length > 0 ? (
                <div className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-amber-600">{t("profile_import.preview.warnings")}</p>
                  <ul className="mt-3 space-y-1 text-[12px] leading-6 text-amber-700">
                    {preview.warnings.map((warning) => (
                      <li key={warning}>- {warning}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>

            <div className="space-y-4">
              <div className="rounded-2xl border border-[var(--border)]/70 bg-[var(--card)] p-4">
                <p className="mb-3 text-[11px] uppercase tracking-[0.22em] text-[var(--muted-foreground)]">{t("profile_import.preview.copa")}</p>
                <MarkdownRenderer content={preview.generated_copa_markdown} />
              </div>
              <div className="rounded-2xl border border-[var(--border)]/70 bg-[var(--card)] p-4">
                <p className="mb-3 text-[11px] uppercase tracking-[0.22em] text-[var(--muted-foreground)]">{t("profile_import.preview.summary")}</p>
                <MarkdownRenderer content={preview.generated_summary_markdown} />
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </Modal>
  );
}
