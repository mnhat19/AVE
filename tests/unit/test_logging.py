from pathlib import Path

from ave.utils.logging import get_logger, setup_logging


def test_setup_logging_no_duplicate_handlers(tmp_path: Path) -> None:
    logger = setup_logging(verbose=True)
    first_count = len(logger.handlers)
    logger = setup_logging(verbose=True)
    second_count = len(logger.handlers)
    assert first_count == second_count
    assert logger.propagate is False


def test_setup_logging_with_file_handler(tmp_path: Path) -> None:
    log_file = tmp_path / "app.log"
    logger = setup_logging(verbose=True, log_file=log_file)
    assert len(logger.handlers) == 2


def test_get_logger_name() -> None:
    logger = get_logger("layer1_ingestion")
    assert logger.name == "ave.layer1_ingestion"
