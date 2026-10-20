# End-to-End Implementation

The repository owner expects implementation work to reach a verified, merged PR,
not stop at local changes. Unless the user limits the task, own this workflow:

1. Work on one issue, keep usage economical, and preserve unrelated changes.
2. Implement the smallest correct change and run the repository verification gates.
3. Commit intended files on a dedicated branch, push, and open a scoped PR.
4. Monitor CI and CodeRabbit/Kilo reviews for the final commit. Address valid
   findings and safely remediable blockers, including dependency-audit failures,
   then rerun affected verification. Monitoring is not a substitute for fixing.
5. Merge only after the exact final head passes all CI checks, both bot reviews
   complete, and material findings and review threads are resolved. Match the
   verified head when merging; never bypass checks or weaken protection.
6. Verify the merge and report the PR URL. Close the issue only when every
   acceptance criterion is satisfied; otherwise document remaining blockers.

If checks outlive the turn, arrange automatic continuation, stop monitoring after
completion, and keep unchanged status checks quiet. Pause for genuine decisions,
unavailable permissions, or unsafe/out-of-scope work rather than silently stopping
at a partial milestone. Respect explicit approval requirements and raise them
before the workflow depends on them.
