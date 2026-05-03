from pathlib import Path

import pandas as pd

from ave.utils.hashing import hash_dataframe, hash_dict, hash_file, hash_string, verify_hash


def test_hash_file_deterministic(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("hello", encoding="utf-8")
    first = hash_file(file_path)
    second = hash_file(file_path)
    assert first == second
    assert len(first) == 64


def test_hash_string_and_verify() -> None:
    value = "test-value"
    digest = hash_string(value)
    assert len(digest) == 64
    assert verify_hash(value, digest)


def test_hash_dict_order_independent() -> None:
    data_a = {"b": 2, "a": 1}
    data_b = {"a": 1, "b": 2}
    assert hash_dict(data_a) == hash_dict(data_b)


def test_hash_dataframe_order_independent() -> None:
    df_a = pd.DataFrame({"b": [2, 1], "a": ["x", "y"]})
    df_b = pd.DataFrame({"a": ["y", "x"], "b": [1, 2]})
    assert hash_dataframe(df_a) == hash_dataframe(df_b)
