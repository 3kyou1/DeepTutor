import test from "node:test";
import assert from "node:assert/strict";

const { applyImportedProfileToMemoryState } = await import(
  new URL("../lib/profile-import-memory.ts", import.meta.url).href
);

test("applyImportedProfileToMemoryState writes imported profile back to memory page state", () => {
  const original = {
    data: {
      summary: "old summary",
      profile: "old profile",
      summary_updated_at: "2026-04-20T10:00:00Z",
      profile_updated_at: "2026-04-20T10:00:00Z",
    },
    editors: {
      summary: "draft summary",
      profile: "draft profile",
    },
  };

  const result = applyImportedProfileToMemoryState(original.data, original.editors, {
    profile: "new imported profile",
    profile_updated_at: "2026-04-22T09:30:00Z",
  });

  assert.deepEqual(result, {
    data: {
      summary: "old summary",
      profile: "new imported profile",
      summary_updated_at: "2026-04-20T10:00:00Z",
      profile_updated_at: "2026-04-22T09:30:00Z",
    },
    editors: {
      summary: "draft summary",
      profile: "new imported profile",
    },
  });
  assert.equal(original.data.profile, "old profile");
  assert.equal(original.editors.profile, "draft profile");
});
