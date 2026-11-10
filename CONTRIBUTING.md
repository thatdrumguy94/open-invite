# Contributing to OpenInvite

Thank you for your interest in contributing to OpenInvite! We welcome community contributions, bug fixes, enhancements, and documentation improvements.

## Development Workflow

1. **Fork and Clone the Repository**:
   ```bash
   git clone https://github.com/your-username/open-invite.git
   cd open-invite
   ```

2. **Set Up a Local Environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt -r requirements-dev.txt
   ```

3. **Run the Test Suite**:
   ```bash
   PYTHONPATH=. pytest -v
   ```
   Ensure all tests pass before making changes.

4. **Make Your Changes**:
   - Write clear, concise code adhering to PEP 8 standards.
   - Include tests in `tests/` covering new features or bug fixes.
   - Maintain documentation integrity and update README.md if adding environment variables.

5. **Submit a Pull Request**:
   - Open a PR against the `main` branch with a clear description of the problem solved.
