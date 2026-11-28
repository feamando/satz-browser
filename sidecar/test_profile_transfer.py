#!/usr/bin/env python3
"""
Tests for offline encrypted Profile Export, Ingest (`Upload profile`),
and UUID-based most-recently-updated bidirectional merge.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

SIDECAR_DIR = Path(__file__).resolve().parent
SGS_ROOT = SIDECAR_DIR.parent.parent / "sgs"
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))
if str(SGS_ROOT) not in sys.path:
    sys.path.insert(0, str(SGS_ROOT))

import satz_passwords
from satz_models import SatzSidecarRuntime, make_sidecar_server
from satz_profile_bundle import export_profile_bundle, import_profile_bundle


class MemoryKeyring:
    """Simulated isolated per-device OS keychain."""

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, user: str) -> str | None:
        return self._data.get((service, user))

    def set_password(self, service: str, user: str, val: str) -> None:
        self._data[(service, user)] = val

    def delete_password(self, service: str, user: str) -> None:
        self._data.pop((service, user), None)


class TestProfileTransferAndUuidMerge(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_a = Path(tempfile.mkdtemp(prefix="satz_test_prof_a_"))
        self.temp_b = Path(tempfile.mkdtemp(prefix="satz_test_prof_b_"))
        self.kr_a = MemoryKeyring()
        self.kr_b = MemoryKeyring()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_a, ignore_errors=True)
        shutil.rmtree(self.temp_b, ignore_errors=True)

    def _new_runtime(self, base_dir: Path, keyring_obj: MemoryKeyring) -> SatzSidecarRuntime:
        with mock.patch.object(satz_passwords, "keyring", keyring_obj):
            rt = SatzSidecarRuntime(sgs_root=SGS_ROOT, store_path=base_dir / "planck_store.sqlite")
            rt.mail.pipeline.stop_worker()
            rt.stop_news_sync_worker()
            return rt

    def test_cross_device_offline_export_and_import_without_source_device_key(self) -> None:
        """
        Exports a profile on Device A, verifies ciphertext hides all metadata & secrets,
        rejects wrong PINs on Device B cleanly, and installs cleanly on Device B with ZERO
        access to Device A's OS keychain.
        """
        with mock.patch.object(satz_passwords, "keyring", self.kr_a):
            rt_a = self._new_runtime(self.temp_a, self.kr_a)
            try:
                created = rt_a.passwords.create_profile("Alice Primary", "123456")
                p_a = created["active_profile"]
                pid_a = p_a["id"]
                uuid_a = p_a["uuid"]
                self.assertTrue(len(uuid_a) >= 32)

                rt_a.passwords.upsert_service_credential(
                    service="OPENAI",
                    username="alice@example.com",
                    api_key="sk-secret-openai-abc123",
                    url="https://api.openai.com",
                )
                rt_a.brain.upsert_entity(
                    entity_type="person",
                    name="Elena Rostova",
                    summary="Lead systems architect",
                    content="Works on distributed browser storage.",
                    tier=1,
                )
                rt_a.set_domain_trust("bbc.com", 9.5)
                rt_a.news.manage_topic({"action": "add", "name": "Quantum Computing", "keywords": ["quantum", "qubit"]})
                with rt_a.store_lock:
                    rt_a.store.db.execute(
                        "INSERT OR REPLACE INTO satz_meta (key, value) VALUES (?, ?)",
                        ("model_role_planner", "gemma-4-e4b"),
                    )
                    rt_a.store.db.commit()

                # Seed a mail account + personalized model weight file + drive state
                with rt_a.mail.db_lock:
                    mc = rt_a.mail._ensure_connection()
                    mc.execute(
                        """
                        INSERT INTO accounts
                          (id, label, email, protocol, in_host, in_port, in_security, smtp_host, smtp_port, smtp_security, vault_prefix, last_sync_at)
                        VALUES (?, ?, ?, 'imap', 'imap.gmail.com', 993, 'ssl', 'smtp.gmail.com', 587, 'starttls', 'GMAIL', 1750000000.0)
                        """,
                        ("acct-1", "Alice Mail", "alice@gmail.com"),
                    )
                    mc.execute("INSERT OR REPLACE INTO mail_settings (key, value) VALUES ('eval_mode', '1')")
                    mc.commit()
                pdir_a = rt_a.passwords.get_profile_dir(pid_a)
                (pdir_a / "mail_model").mkdir(parents=True, exist_ok=True)
                (pdir_a / "mail_model" / "weights.json").write_text('{"acc": 0.96}', encoding="utf-8")

                with rt_a.drives._db_lock:
                    dc = rt_a.drives._get_conn()
                    dc.execute(
                        """
                        INSERT INTO drive_sync_state (provider, account_email, account_name, delta_token, last_synced_at, total_files, status)
                        VALUES ('gdrive', 'alice@gmail.com', 'Alice Drive', 'tok_abc', 1750000000.0, 42, 'idle')
                        """
                    )
                    dc.commit()

                exported = export_profile_bundle(rt_a, profile_id=pid_a)
                bundle_bytes = base64.b64decode(exported["bundle_b64"])
                envelope = json.loads(bundle_bytes.decode("utf-8"))
                self.assertEqual(envelope["format"], "satz-profile-v1")
                raw_text = bundle_bytes.decode("utf-8")
                self.assertNotIn("Alice Primary", raw_text)
                self.assertNotIn(uuid_a, raw_text)
                self.assertNotIn("sk-secret-openai-abc123", raw_text)
                self.assertNotIn("Elena Rostova", raw_text)
            finally:
                rt_a.close()

        # Simulate Device B with completely fresh OS Keychain (self.kr_b)
        with mock.patch.object(satz_passwords, "keyring", self.kr_b):
            rt_b = self._new_runtime(self.temp_b, self.kr_b)
            try:
                # Wrong PIN must fail cleanly with zero profile installed
                with self.assertRaises(ValueError):
                    import_profile_bundle(rt_b, bundle_bytes, "000000")
                self.assertEqual(rt_b.passwords.list_profiles()["profiles"], [])

                # Correct PIN installs and unlocks on Device B cleanly
                res = import_profile_bundle(rt_b, bundle_bytes, "123456")
                self.assertEqual(res["import_action"], "create")
                self.assertTrue(res["unlocked"])
                self.assertEqual(res["active_profile"]["uuid"], uuid_a)
                self.assertEqual(res["active_profile"]["name"], "Alice Primary")

                # Vault decrypted with Device B's new keychain key works
                self.assertEqual(rt_b.passwords.get_provider_secret("OPENAI", "api_key"), "sk-secret-openai-abc123")
                # Lock and unlock on Device B again using Device B keychain
                rt_b.passwords.lock_profile()
                rt_b.passwords.unlock_profile(res["active_profile_id"], "123456")
                self.assertEqual(rt_b.passwords.get_provider_secret("OPENAI", "api_key"), "sk-secret-openai-abc123")

                # Brain, Trust, News topic, Meta, Mail, Drives restored cleanly
                ent = rt_b.brain.get_entity("elena-rostova")
                self.assertIsNotNone(ent)
                self.assertIn("Lead systems architect", str(ent.get("summary") or ""))

                self.assertEqual(round(rt_b.store.trust("bbc.com")["personal"], 1), 9.5)
                topics = [
                    str(r["name"])
                    for r in rt_b.store.db.execute("SELECT name FROM satz_news_topics").fetchall()
                ]
                self.assertIn("Quantum Computing", topics)

                with rt_b.store_lock:
                    row = rt_b.store.db.execute(
                        "SELECT value FROM satz_meta WHERE key = 'model_role_planner'"
                    ).fetchone()
                    self.assertEqual(row["value"], "gemma-4-e4b")

                with rt_b.mail.db_lock:
                    mc_b = rt_b.mail._ensure_connection()
                    acct = mc_b.execute("SELECT email, last_sync_at FROM accounts WHERE id = 'acct-1'").fetchone()
                    self.assertEqual(acct["email"], "alice@gmail.com")
                    # Reset on empty local inbox so Device B syncs full mail
                    self.assertEqual(float(acct["last_sync_at"]), 0.0)
                    ms = mc_b.execute("SELECT value FROM mail_settings WHERE key = 'eval_mode'").fetchone()
                    self.assertEqual(ms["value"], "1")
                pdir_b = rt_b.passwords.get_profile_dir(res["active_profile_id"])
                self.assertTrue((pdir_b / "mail_model" / "weights.json").exists())

                with rt_b.drives._db_lock:
                    dc_b = rt_b.drives._get_conn()
                    ds = dc_b.execute("SELECT account_email, delta_token FROM drive_sync_state WHERE provider = 'gdrive'").fetchone()
                    self.assertEqual(ds["account_email"], "alice@gmail.com")
                    self.assertEqual(ds["delta_token"], "")
            finally:
                rt_b.close()

    def test_slug_collision_with_distinct_uuid_creates_separate_profile(self) -> None:
        with mock.patch.object(satz_passwords, "keyring", self.kr_a):
            rt_a = self._new_runtime(self.temp_a, self.kr_a)
            try:
                rt_a.passwords.create_profile("Work", "111111")
                rt_a.passwords.upsert_service_credential(service="GITHUB", api_key="ghp_from_a")
                exp_a = export_profile_bundle(rt_a)
                bundle_a = base64.b64decode(exp_a["bundle_b64"])
            finally:
                rt_a.close()

        with mock.patch.object(satz_passwords, "keyring", self.kr_b):
            rt_b = self._new_runtime(self.temp_b, self.kr_b)
            try:
                created_b = rt_b.passwords.create_profile("Work", "222222")
                rt_b.passwords.upsert_service_credential(service="GITHUB", api_key="ghp_from_b")
                uuid_b = created_b["active_profile"]["uuid"]

                res = import_profile_bundle(rt_b, bundle_a, "111111")
                self.assertEqual(res["import_action"], "create")
                self.assertEqual(res["imported_profile_id"], "work-2")
                self.assertNotEqual(res["imported_profile_uuid"], uuid_b)
                self.assertEqual(len(res["profiles"]), 2)
                self.assertEqual(rt_b.passwords.get_provider_secret("GITHUB", "api_key"), "ghp_from_a")

                rt_b.passwords.unlock_profile("work", "222222")
                self.assertEqual(rt_b.passwords.get_provider_secret("GITHUB", "api_key"), "ghp_from_b")
            finally:
                rt_b.close()

    def test_same_uuid_bidirectional_most_recent_updated_wins(self) -> None:
        """
        Tests bidirectional merge on identical UUID:
        - Newer setting/credential/Brain/topic/trust on EITHER side wins.
        - Importing an OLDER snapshot onto a NEWER device preserves the NEWER device's edits.
        - Importing a NEWER snapshot onto an OLDER device updates with the NEWER edits.
        """
        # 1. Create baseline on Device A (T0) and export to Device B
        with mock.patch.object(satz_passwords, "keyring", self.kr_a):
            rt_a = self._new_runtime(self.temp_a, self.kr_a)
            try:
                rt_a.passwords.create_profile("SyncProfile", "555555")
                rt_a.passwords.upsert_service_credential(service="BRAVE", api_key="brave_t0")
                rt_a.passwords.upsert_service_credential(service="ANTHROPIC", api_key="anth_t0")
                rt_a.brain.upsert_entity(
                    entity_type="project",
                    name="Project Helios",
                    summary="Summary T0",
                    content="Initial content",
                )
                rt_a.set_domain_trust("example.com", 6.0)
                with rt_a.store_lock:
                    rt_a.store.db.execute(
                        "INSERT OR REPLACE INTO satz_meta (key, value) VALUES ('planner_model', 'model_t0')"
                    )
                    rt_a.store.db.execute(
                        "INSERT OR REPLACE INTO satz_meta (key, value) VALUES ('reader_model', 'reader_t0')"
                    )
                    rt_a.store.db.commit()
                bundle_t0 = base64.b64decode(export_profile_bundle(rt_a)["bundle_b64"])
            finally:
                pass

        with mock.patch.object(satz_passwords, "keyring", self.kr_b):
            rt_b = self._new_runtime(self.temp_b, self.kr_b)
            import_profile_bundle(rt_b, bundle_t0, "555555")

        # 2. At T1 (~+0.05s or explicit newer epoch), Device A updates ANTHROPIC & deletes BRAVE? No, let's split edits!
        # Wait briefly so SQLite julianday('now') and time.time() strictly advance between T1 and T2.
        time.sleep(0.08)
        with mock.patch.object(satz_passwords, "keyring", self.kr_a):
            # T1 on Device A: updates planner_model, BRAVE key, adds entity "Note From A"
            rt_a.passwords.upsert_service_credential(service="BRAVE", api_key="brave_t1_from_a")
            rt_a.passwords.delete_service_credential("ANTHROPIC")
            rt_a.brain.upsert_entity(
                entity_type="note",
                name="Note From A",
                summary="Created at T1",
                content="Content A",
            )
            rt_a.set_domain_trust("example.com", 8.0)
            with rt_a.store_lock:
                rt_a.store.db.execute(
                    "INSERT OR REPLACE INTO satz_meta (key, value) VALUES ('planner_model', 'model_t1_from_a')"
                )
                rt_a.store.db.commit()
            bundle_a_t1 = base64.b64decode(export_profile_bundle(rt_a)["bundle_b64"])

        # T2 on Device B (> T1): updates reader_model, BRAVE key EVEN NEWER, updates Project Helios, updates trust EVEN NEWER
        time.sleep(1.1)  # YAML frontmatter & ISO strings use 1-second resolution
        with mock.patch.object(satz_passwords, "keyring", self.kr_b):
            rt_b.passwords.upsert_service_credential(service="BRAVE", api_key="brave_t2_from_b")
            rt_b.brain.upsert_entity(
                entity_type="project",
                name="Project Helios",
                summary="Summary T2 Newer",
                content="Updated on B",
            )
            rt_b.set_domain_trust("example.com", 9.8)
            with rt_b.store_lock:
                rt_b.store.db.execute(
                    "INSERT OR REPLACE INTO satz_meta (key, value) VALUES ('reader_model', 'reader_t2_from_b')"
                )
                rt_b.store.db.commit()

            # Import A@T1 INTO B@T2 -> B should:
            # - gain T1's planner_model='model_t1_from_a' (newer than B's T0)
            # - KEEP B's T2 reader_model='reader_t2_from_b'
            # - KEEP B's T2 brave_t2_from_b (newer than A's T1)
            # - APPLY A's T1 tombstone deleting ANTHROPIC (newer than B's T0)
            # - KEEP B's T2 Project Helios & trust=9.8
            # - GAIN A's T1 Note From A
            merged_b = import_profile_bundle(rt_b, bundle_a_t1, "555555")
            self.assertEqual(merged_b["import_action"], "merge")
            self.assertEqual(rt_b.passwords.get_provider_secret("BRAVE", "api_key"), "brave_t2_from_b")
            self.assertEqual(rt_b.passwords.get_provider_secret("ANTHROPIC", "api_key"), "")
            self.assertIsNotNone(rt_b.brain.get_entity("note-from-a"))
            helios = rt_b.brain.get_entity("project-helios")
            self.assertEqual(helios["summary"], "Summary T2 Newer")
            self.assertEqual(round(rt_b.store.trust("example.com")["personal"], 1), 9.8)
            with rt_b.store_lock:
                pm = rt_b.store.db.execute("SELECT value FROM satz_meta WHERE key = 'planner_model'").fetchone()
                rm = rt_b.store.db.execute("SELECT value FROM satz_meta WHERE key = 'reader_model'").fetchone()
                self.assertEqual(pm["value"], "model_t1_from_a")
                self.assertEqual(rm["value"], "reader_t2_from_b")

            bundle_b_merged = base64.b64decode(export_profile_bundle(rt_b)["bundle_b64"])
            rt_b.close()

        # Import merged B@T2 INTO older Device A@T1 -> Device A catches up cleanly!
        with mock.patch.object(satz_passwords, "keyring", self.kr_a):
            try:
                merged_a = import_profile_bundle(rt_a, bundle_b_merged, "555555")
                self.assertEqual(merged_a["import_action"], "merge")
                self.assertEqual(rt_a.passwords.get_provider_secret("BRAVE", "api_key"), "brave_t2_from_b")
                self.assertEqual(rt_a.passwords.get_provider_secret("ANTHROPIC", "api_key"), "")
                self.assertEqual(rt_a.brain.get_entity("project-helios")["summary"], "Summary T2 Newer")
                self.assertEqual(round(rt_a.store.trust("example.com")["personal"], 1), 9.8)
                with rt_a.store_lock:
                    pm = rt_a.store.db.execute("SELECT value FROM satz_meta WHERE key = 'planner_model'").fetchone()
                    rm = rt_a.store.db.execute("SELECT value FROM satz_meta WHERE key = 'reader_model'").fetchone()
                    self.assertEqual(pm["value"], "model_t1_from_a")
                    self.assertEqual(rm["value"], "reader_t2_from_b")
            finally:
                rt_a.close()

    def test_http_export_and_sse_import_endpoints(self) -> None:
        with mock.patch.object(satz_passwords, "keyring", self.kr_a):
            rt_a = self._new_runtime(self.temp_a, self.kr_a)
            srv_a = make_sidecar_server(rt_a, host="127.0.0.1", port=0, auth_token="tok-a")
            threading.Thread(target=srv_a.serve_forever, daemon=True).start()
            try:
                port_a = srv_a.server_address[1]
                rt_a.passwords.create_profile("HttpUser", "777777")
                rt_a.passwords.upsert_service_credential(service="DEEPSEEK", api_key="sk-ds-test-123")

                req_exp = urllib.request.Request(
                    f"http://127.0.0.1:{port_a}/profile/export",
                    data=json.dumps({}).encode("utf-8"),
                    headers={"Content-Type": "application/json", "X-Satz-Token": "tok-a"},
                    method="POST",
                )
                with urllib.request.urlopen(req_exp, timeout=30) as resp:
                    exp_json = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(exp_json["ok"])
                self.assertTrue(exp_json["filename"].endswith(".satzprofile"))
                bundle_b64 = exp_json["bundle_b64"]
            finally:
                srv_a.shutdown()
                srv_a.server_close()
                rt_a.close()

        with mock.patch.object(satz_passwords, "keyring", self.kr_b):
            rt_b = self._new_runtime(self.temp_b, self.kr_b)
            srv_b = make_sidecar_server(rt_b, host="127.0.0.1", port=0, auth_token="tok-b")
            threading.Thread(target=srv_b.serve_forever, daemon=True).start()
            try:
                port_b = srv_b.server_address[1]
                req_imp = urllib.request.Request(
                    f"http://127.0.0.1:{port_b}/profile/import",
                    data=json.dumps({"bundle_b64": bundle_b64, "pin": "777777", "stream": True}).encode("utf-8"),
                    headers={"Content-Type": "application/json", "X-Satz-Token": "tok-b"},
                    method="POST",
                )
                events = []
                with urllib.request.urlopen(req_imp, timeout=45) as resp:
                    for raw_line in resp:
                        line = raw_line.decode("utf-8").strip()
                        if line.startswith("data: "):
                            events.append(json.loads(line[6:]))
                final_ev = [ev for ev in events if ev.get("done")]
                self.assertEqual(len(final_ev), 1)
                self.assertTrue(final_ev[0]["ok"])
                self.assertEqual(final_ev[0]["import_action"], "create")
                self.assertEqual(rt_b.passwords.get_provider_secret("DEEPSEEK", "api_key"), "sk-ds-test-123")
            finally:
                srv_b.shutdown()
                srv_b.server_close()
                rt_b.close()

    def test_same_uuid_different_local_pin_and_topic_tombstones(self) -> None:
        with mock.patch.object(satz_passwords, "keyring", self.kr_a):
            rt_a = self._new_runtime(self.temp_a, self.kr_a)
            try:
                rt_a.passwords.create_profile("DualPin", "112233")
                rt_a.passwords.upsert_service_credential(service="GROQ", api_key="gsk_from_a")
                rt_a.news.manage_topic({"action": "add", "name": "Temp Topic", "keywords": ["temp"]})
                tid = str(
                    rt_a.store.db.execute(
                        "SELECT topic_id FROM satz_news_topics WHERE name = 'Temp Topic'"
                    ).fetchone()["topic_id"]
                )
                bundle_t0 = base64.b64decode(export_profile_bundle(rt_a)["bundle_b64"])

                time.sleep(0.08)
                rt_a.news.manage_topic({"action": "delete", "topic_id": tid})
                rt_a.passwords.upsert_service_credential(service="GROQ", api_key="gsk_newer_from_a")
                bundle_t1 = base64.b64decode(export_profile_bundle(rt_a)["bundle_b64"])
            finally:
                rt_a.close()

        with mock.patch.object(satz_passwords, "keyring", self.kr_b):
            rt_b = self._new_runtime(self.temp_b, self.kr_b)
            try:
                res0 = import_profile_bundle(rt_b, bundle_t0, "112233")
                pid_b = res0["imported_profile_id"]
                self.assertEqual(
                    rt_b.store.db.execute("SELECT COUNT(*) FROM satz_news_topics WHERE topic_id = ?", (tid,)).fetchone()[0],
                    1,
                )

                # Re-seal local vault on Device B with a distinct PIN ("998877") and lock
                env_b = dict(rt_b.passwords._unlocked_env_cache)
                meta_b = dict(rt_b.passwords._unlocked_meta_ts_cache)
                rt_b.passwords._active_pin = "998877"
                rt_b.passwords._persist_active_vault(env_b, meta_ts=meta_b)
                rt_b.passwords.lock_profile()

                # Attempting to merge T1 (PIN 112233) without local_pin asks clearly for local PIN
                with self.assertRaises(ValueError) as ctx:
                    import_profile_bundle(rt_b, bundle_t1, "112233")
                self.assertIn("local PIN", str(ctx.exception))

                # Providing local_pin="998877" decrypts both, merges tombstones + newer key, and unlocks
                res1 = import_profile_bundle(rt_b, bundle_t1, "112233", local_pin="998877")
                self.assertEqual(res1["import_action"], "merge")
                self.assertEqual(res1["imported_profile_id"], pid_b)
                self.assertEqual(rt_b.passwords.get_provider_secret("GROQ", "api_key"), "gsk_newer_from_a")
                self.assertEqual(
                    rt_b.store.db.execute("SELECT COUNT(*) FROM satz_news_topics WHERE topic_id = ?", (tid,)).fetchone()[0],
                    0,
                )
            finally:
                rt_b.close()


if __name__ == "__main__":
    unittest.main()
