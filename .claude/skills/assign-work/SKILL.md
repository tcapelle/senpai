---
name: assign-work
description: Use this skill to distribute research hypotheses to idle students by creating experiment branches and draft PRs. For each idle student, creates a branch from the advisor branch, pushes it, and opens a labeled draft PR with the hypothesis, instructions, and baseline metrics.
---

# Assign Work to Students

For each idle student (no `status:wip` PR), create a branch and draft PR assigning them a hypothesis.

## Steps per assignment

1. Ensure you're on the latest advisor branch:
```bash
git checkout <advisor-branch> && git pull origin <advisor-branch>
```

2. Create an experiment branch:
```bash
git checkout -b exp/<hypothesis-name>
git push -u origin exp/<hypothesis-name>
```

3. Create a labeled draft PR:
```bash
gh pr create --draft \
  --title "<hypothesis title>" \
  --body "<PR body — use template below>" \
  --label "senpai" --label "student:<name>" --label "status:wip" \
  --base <advisor-branch> --head exp/<hypothesis-name>
```

4. Return to the advisor branch before the next assignment:
```bash
git checkout <advisor-branch>
```

## PR body template

Every PR must follow this structure:

```markdown
## Hypothesis
<what we think will improve metrics and why>

## Instructions
<specific changes to make to structured_split/structured_train.py — be concrete>

## Baseline
<current best metrics for reference>

---

## Results
_To be filled by student_
```

## Writing good instructions

- **Be specific.** "Try a higher learning rate" is vague. "Change lr from 5e-4 to 1e-3 and add cosine annealing with T_max=epochs" is actionable.
- **Always include baseline metrics.** Students need a concrete target to compare against.
- **Use `--wandb_group`** in instructions when a hypothesis needs multiple iterations (e.g., trying several values of the same hyperparameter).
- **One hypothesis per PR.** Bundling changes makes it impossible to attribute what worked.

## Matching hypotheses to students

- If there are more hypotheses than idle students, pick the most promising ones.
- If there are more idle students than hypotheses, note which students still need work — the advisor should generate more ideas.
- Avoid assigning the same idea to multiple students. Check what's already in-flight.
