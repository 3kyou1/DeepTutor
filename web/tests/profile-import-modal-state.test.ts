import test from "node:test";
import assert from "node:assert/strict";

const {
  canApplyProfileImport,
  toProfileImportApplyStatus,
} = await import(new URL("../lib/profile-import-modal-state.ts", import.meta.url).href);

test("toProfileImportApplyStatus keeps apply feedback visible after a successful import", () => {
  const status = toProfileImportApplyStatus({
    updated_sections: ["CoPA Factors", "Profile Summary"],
    profile_updated_at: "2026-04-22T12:30:00Z",
  });

  assert.deepEqual(status, {
    updatedSections: ["CoPA Factors", "Profile Summary"],
    profileUpdatedAt: "2026-04-22T12:30:00Z",
  });
});

test("canApplyProfileImport blocks duplicate apply while preserving preview state after success", () => {
  assert.equal(canApplyProfileImport({ canApply: true, applying: false, applied: false }), true);
  assert.equal(canApplyProfileImport({ canApply: false, applying: false, applied: false }), false);
  assert.equal(canApplyProfileImport({ canApply: true, applying: true, applied: false }), false);
  assert.equal(canApplyProfileImport({ canApply: true, applying: false, applied: true }), false);
});
