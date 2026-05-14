# Contributing

Thank you for taking the time to contribute to this project!

## Reporting Bugs

If you find a bug, please open an **Issue** with details about:
- Current behavior
- Expected behavior
- Steps to reproduce the problem

## Workflow

The most up-to-date branch in this project is always **`main`**. All contributions should start from it and Pull Requests should be opened against `main`.

1. **Fork** the repository
2. Create a branch for your changes:
   ```bash
   git checkout -b feature/feature-name
   ```
3. Make your changes and commit them (see the Commits section below)
4. Push your branch to your fork:
   ```bash
   git push origin feature/feature-name
   ```
5. Open a **Pull Request (PR)** against the `main` branch of the original repository

## Semantic Commits

We use the **Semantic Commit (Conventional Commits)** standard. Your commits should follow this format:

`type: short description`

**Common types:**
- `feat`: A new feature
- `fix`: A bug fix
- `docs`: Documentation changes
- `style`: Changes that don't affect code meaning (whitespace, formatting, etc)
- `refactor`: Code changes that don't fix bugs or add features
- `test`: Adding or updating tests
- `chore`: Build task updates, packages, etc

Example: `feat: add login system`

## Pull Request Requirements

- Code must be readable and follow project standards
- Briefly describe what was done in the PR
- Ensure your branch is up to date with the original `main` before submitting
- For code contributions: run tests locally and verify they pass
- For documentation contributions: review formatting and clarity
