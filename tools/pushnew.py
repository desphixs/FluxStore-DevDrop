import argparse
import subprocess as sp
import sys
from datetime import datetime

def run(cmd, check=True, capture=False):
    if capture:
        return sp.check_output(cmd, shell=False).decode().strip()
    if check:
        sp.check_call(cmd, shell=False)
        return ""
    else:
        return sp.call(cmd, shell=False)

def current_branch():
    return run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture=True)

def short_sha():
    return run(["git", "rev-parse", "--short", "HEAD"], capture=True)

def has_changes():
    # unstaged or staged diffs?
    out = run(["git", "status", "--porcelain"], capture=True)
    return bool(out.strip())

def list_remotes():
    remotes = run(["git", "remote"], capture=True).splitlines()
    return [r.strip() for r in remotes if r.strip()]

def main():
    p = argparse.ArgumentParser(description="Push HEAD to a new branch on all remotes.")
    p.add_argument("-b", "--branch", help="Branch name to create on each remote. If omitted, one is generated.")
    p.add_argument("-m", "--message", help="Commit message to use before pushing. If omitted, no commit is created.")
    p.add_argument("--add-all", action="store_true", help="Run `git add -A` before committing.")
    p.add_argument("--allow-empty", action="store_true", help="Allow an empty commit if no changes.")
    p.add_argument("--no-verify", action="store_true", help="Pass --no-verify to commit.")
    args = p.parse_args()

    # Derive branch name if not provided: <local>-<YYYYmmdd-HHMM>-<sha>
    base = current_branch()
    sha = short_sha()
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    target_branch = args.branch or f"{base}-{ts}-{sha}"

    # Optional commit
    if args.message:
        if args.add_all:
            run(["git", "add", "-A"])
        dirty = has_changes()
        commit_cmd = ["git", "commit", "-m", args.message]
        if args.no_verify:
            commit_cmd.append("--no-verify")
        if dirty:
            run(commit_cmd)
        elif args.allow_empty:
            run(commit_cmd + ["--allow-empty"])
        else:
            print("No changes to commit (use --add-all to stage or --allow-empty to force).")

    remotes = list_remotes()
    if not remotes:
        print("No remotes configured in this repo.")
        sys.exit(1)

    # Push HEAD to refs/heads/<target_branch> on every remote
    for r in remotes:
        print(f"Pushing to {r} -> {target_branch}")
        run(["git", "push", r, f"HEAD:refs/heads/{target_branch}"])

    print("\nDone.")
    print(f"Created/updated branch `{target_branch}` on: {', '.join(remotes)}")

if __name__ == "__main__":
    main()
