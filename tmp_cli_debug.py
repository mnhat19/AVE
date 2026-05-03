from typer.testing import CliRunner

from ave.cli import app

runner = CliRunner()
result = runner.invoke(app, ["run", "--help"])
print("exit_code", result.exit_code)
print("stdout:\n", result.stdout)
print("stderr:\n", result.stderr)
print("exception:\n", result.exception)
