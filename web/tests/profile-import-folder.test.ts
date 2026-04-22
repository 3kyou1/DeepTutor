import test from "node:test";
import assert from "node:assert/strict";

const {
  buildProviderFolderSelection,
  shouldIncludeProviderHistoryFile,
} = await import(new URL("../lib/profile-import-folder.ts", import.meta.url).href);

test("shouldIncludeProviderHistoryFile keeps only codex rollout jsonl files", () => {
  assert.equal(
    shouldIncludeProviderHistoryFile("codex", "sessions/2026/04/22/rollout-1.jsonl"),
    true,
  );
  assert.equal(
    shouldIncludeProviderHistoryFile("codex", "archived_sessions/2026/04/22/rollout-2.jsonl"),
    true,
  );
  assert.equal(shouldIncludeProviderHistoryFile("codex", "history.jsonl"), false);
  assert.equal(shouldIncludeProviderHistoryFile("codex", "logs_2.sqlite"), false);
  assert.equal(shouldIncludeProviderHistoryFile("codex", "memories/foo.md"), false);
});

test("buildProviderFolderSelection prefers Codex project names inferred from rollout metadata", async () => {
  const selection = await buildProviderFolderSelection("codex", [
    {
      name: "rollout-1.jsonl",
      size: 120,
      webkitRelativePath: ".codex/sessions/2026/04/22/rollout-1.jsonl",
      file: {
        id: "keep-1",
        text: async () =>
          [
            JSON.stringify({
              type: "session_meta",
              payload: { cwd: "/Users/hangsu/Desktop/DeepTutor" },
            }),
            JSON.stringify({ type: "response_item" }),
          ].join("\n"),
      },
    },
    {
      name: "rollout-2.jsonl",
      size: 80,
      webkitRelativePath: ".codex/archived_sessions/2026/04/20/rollout-2.jsonl",
      file: {
        id: "keep-2",
        text: async () =>
          JSON.stringify({
            type: "session_meta",
            payload: { cwd: "/Users/hangsu/Desktop/DeepTutor" },
          }),
      },
    },
    {
      name: "logs_2.sqlite",
      size: 400_000_000,
      webkitRelativePath: ".codex/logs_2.sqlite",
      file: { id: "drop-1" },
    },
    {
      name: "auth.json",
      size: 200,
      webkitRelativePath: ".codex/auth.json",
      file: { id: "drop-2" },
    },
  ]);

  assert.equal(selection.rootName, ".codex");
  assert.equal(selection.totalFileCount, 4);
  assert.equal(selection.totalBytes, 400_000_400);
  assert.equal(selection.files.length, 2);
  assert.equal(selection.filteredBytes, 200);
  assert.equal(selection.groups.length, 1);
  assert.equal(selection.groups[0]?.label, "DeepTutor");
  assert.equal(selection.groups[0]?.hint, "~/Desktop/DeepTutor");
  assert.deepEqual(
    selection.files.map((item: { relative_path: string }) => item.relative_path),
    [
      "sessions/2026/04/22/rollout-1.jsonl",
      "archived_sessions/2026/04/20/rollout-2.jsonl",
    ],
  );
});

test("buildProviderFolderSelection uses Claude project basename as label", async () => {
  const selection = await buildProviderFolderSelection("claude_code", [
    {
      name: "session-a.jsonl",
      size: 120,
      webkitRelativePath:
        ".claude/projects/-Users-hangsu-Desktop-DeepTutor/session-a.jsonl",
      file: { id: "a" },
    },
    {
      name: "session-b.jsonl",
      size: 80,
      webkitRelativePath:
        ".claude/projects/-Users-hangsu-Desktop-DeepTutor/session-b.jsonl",
      file: { id: "b" },
    },
    {
      name: "settings.json",
      size: 20,
      webkitRelativePath: ".claude/settings.json",
      file: { id: "ignore" },
    },
  ]);

  assert.equal(selection.files.length, 2);
  assert.equal(selection.groups.length, 1);
  assert.equal(selection.groups[0]?.label, "DeepTutor");
  assert.equal(selection.groups[0]?.hint, "~/Desktop/DeepTutor");
  assert.equal(selection.groups[0]?.files.length, 2);
  assert.deepEqual(
    selection.groups[0]?.files.map((item: { relative_path: string }) => item.relative_path),
    [
      "projects/-Users-hangsu-Desktop-DeepTutor/session-a.jsonl",
      "projects/-Users-hangsu-Desktop-DeepTutor/session-b.jsonl",
    ],
  );
});

test("buildProviderFolderSelection prefers Cursor workspace names from workspace.json", async () => {
  const selection = await buildProviderFolderSelection("cursor", [
    {
      name: "workspace.json",
      size: 50,
      webkitRelativePath: "User/workspaceStorage/workspace-123/workspace.json",
      file: {
        id: "workspace-meta",
        text: async () => JSON.stringify({ folder: "file:///Users/hangsu/Desktop/DeepTutor" }),
      },
    },
    {
      name: "state.vscdb",
      size: 120,
      webkitRelativePath: "User/workspaceStorage/workspace-123/state.vscdb",
      file: { id: "workspace-db" },
    },
    {
      name: "state.vscdb-wal",
      size: 80,
      webkitRelativePath: "User/globalStorage/state.vscdb-wal",
      file: { id: "global-wal" },
    },
  ]);

  assert.equal(selection.groups.length, 2);
  const globalGroup = selection.groups.find((group: { label: string }) => group.label === "Global Storage");
  const projectGroup = selection.groups.find((group: { label: string }) => group.label === "DeepTutor");
  assert.ok(globalGroup);
  assert.ok(projectGroup);
  assert.equal(projectGroup?.hint, "~/Desktop/DeepTutor");
});

test("buildProviderFolderSelection falls back to Cursor workspace buckets when project name is unknown", async () => {
  const selection = await buildProviderFolderSelection("cursor", [
    {
      name: "state.vscdb",
      size: 120,
      webkitRelativePath: "User/workspaceStorage/workspace-123/state.vscdb",
      file: { id: "workspace-db" },
    },
    {
      name: "state.vscdb-wal",
      size: 80,
      webkitRelativePath: "User/globalStorage/state.vscdb-wal",
      file: { id: "global-wal" },
    },
  ]);

  assert.equal(selection.groups.length, 2);
  assert.ok(selection.groups.some((group: { label: string }) => group.label === "Global Storage"));
  assert.ok(
    selection.groups.some((group: { label: string }) => group.label === "Workspace workspace-123"),
  );
});

test("buildProviderFolderSelection keeps session buckets when Codex metadata has no project path", async () => {
  const selection = await buildProviderFolderSelection("codex", [
    {
      name: "rollout-1.jsonl",
      size: 120,
      webkitRelativePath: ".codex/sessions/2026/04/22/rollout-1.jsonl",
      file: {
        id: "keep-1",
        text: async () => JSON.stringify({ type: "response_item" }),
      },
    },
  ]);

  assert.equal(selection.groups.length, 1);
  assert.equal(selection.groups[0]?.label, "sessions / 2026/04/22");
});
