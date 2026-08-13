"""Update password to Exzelon@2631 for all untested mailboxes, then test connections."""
import sys
import time
import json
import requests

API_BASE = "https://ra.partnerwithus.tech/api/v1"
LOGIN_USER = "ali.aitechs@gmail.com"
LOGIN_PASS = "SA@Admin#123"
NEW_PASSWORD = "Exzelon@2631"


def login() -> str:
    resp = requests.post(f"{API_BASE}/auth/login", data={
        "username": LOGIN_USER, "password": LOGIN_PASS,
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


def main():
    print("=" * 60)
    print("BULK PASSWORD UPDATE + CONNECTION TEST")
    print(f"New password: {NEW_PASSWORD}")
    print("=" * 60)

    # 1. Login
    token = login()
    headers = {"Authorization": f"Bearer {token}"}
    print("Authenticated OK\n")

    # 2. Get all mailboxes
    resp = requests.get(f"{API_BASE}/mailboxes", headers=headers,
                        params={"limit": 600}, timeout=15)
    data = resp.json()
    all_items = data["items"]

    # Find untested ones (exclude the original 5 @exzelon.com mailboxes)
    untested = [m for m in all_items
                if m.get("connection_status") in ("untested", None, "")]
    print(f"Total mailboxes: {data['total']}")
    print(f"Untested: {len(untested)}")

    if not untested:
        print("Nothing to update!")
        return

    # 3. Update password and test each
    success = 0
    smtp_fail = 0
    update_fail = 0
    results = []
    batch_size = 50

    for i, mb in enumerate(untested):
        mid = mb["mailbox_id"]
        email = mb["email"]

        # Re-auth every 150 requests
        if i > 0 and i % 150 == 0:
            try:
                token = login()
                headers = {"Authorization": f"Bearer {token}"}
                print(f"  [Re-authenticated at {i}/{len(untested)}]")
            except Exception:
                pass

        # Step A: Update password
        try:
            upd_resp = requests.put(f"{API_BASE}/mailboxes/{mid}",
                                    headers=headers,
                                    json={"password": NEW_PASSWORD},
                                    timeout=15)
            if upd_resp.status_code not in (200, 204):
                update_fail += 1
                results.append({"id": mid, "email": email, "status": "update_failed",
                                "detail": upd_resp.text[:100]})
                if update_fail <= 3:
                    print(f"  UPDATE FAIL: {email} -> {upd_resp.status_code}")
                continue
        except Exception as e:
            update_fail += 1
            results.append({"id": mid, "email": email, "status": "update_error",
                            "detail": str(e)[:100]})
            continue

        # Step B: Test connection
        try:
            test_resp = requests.post(f"{API_BASE}/mailboxes/{mid}/test-connection",
                                      headers=headers, timeout=60)
            test_data = test_resp.json()
            if test_data.get("success"):
                success += 1
                results.append({"id": mid, "email": email, "status": "success"})
            else:
                smtp_fail += 1
                results.append({"id": mid, "email": email, "status": "test_failed",
                                "detail": test_data.get("message", "")[:100]})
        except Exception as e:
            smtp_fail += 1
            results.append({"id": mid, "email": email, "status": "test_error",
                            "detail": str(e)[:100]})

        # Progress
        done = i + 1
        if done % batch_size == 0 or done == len(untested):
            print(f"  Progress: {done}/{len(untested)} "
                  f"(success={success}, smtp_fail={smtp_fail}, update_fail={update_fail})")

        # Small delay to avoid overwhelming the server
        if done % 10 == 0:
            time.sleep(0.5)

    print(f"\n{'='*60}")
    print(f"FINAL RESULTS")
    print(f"{'='*60}")
    print(f"  Processed: {len(untested)}")
    print(f"  Connection Success: {success}")
    print(f"  Connection Failed: {smtp_fail}")
    print(f"  Password Update Failed: {update_fail}")

    # Show first few failures
    failures = [r for r in results if r["status"] != "success"]
    if failures:
        print(f"\n  Sample failures ({min(len(failures), 10)} of {len(failures)}):")
        for f in failures[:10]:
            print(f"    {f['email']}: {f.get('detail', f['status'])[:80]}")

    # Save results
    with open("bulk_test_results.json", "w") as fh:
        json.dump({
            "total": len(untested),
            "success": success,
            "smtp_fail": smtp_fail,
            "update_fail": update_fail,
            "details": results,
        }, fh, indent=2)
    print(f"\nFull results saved to bulk_test_results.json")


if __name__ == "__main__":
    main()
