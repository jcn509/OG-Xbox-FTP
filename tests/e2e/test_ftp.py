"""Test the basic functions of the FTP client

Currently only tests whatever is needed for pyxboxtest
"""
from ftplib import FTP
import random
import string
import os

import git
import pytest

from pyxboxtest.xqemu import XQEMUXboxAppRunner
from pyxboxtest.xqemu.hdd import XQEMUHDDTemplate

_BLANK_HDD_DRIVES = (
    "C",
    "E",
    "F",
    "X",
    "Y",
    "Z",
)


@pytest.fixture
def ftp_app(xqemu_blank_hdd_template: XQEMUHDDTemplate):
    repo = git.Repo(".", search_parent_directories=True)
    with XQEMUXboxAppRunner(
        hdd_filename=xqemu_blank_hdd_template.create_fresh_hdd(),
        dvd_filename=os.path.join(repo.working_tree_dir, "OGXboxFTP.iso"),
    ) as app:
        yield app


@pytest.fixture
def ftp_client(ftp_app: XQEMUXboxAppRunner) -> FTP:
    return ftp_app.get_ftp_client("xbox", "xbox")


def test_ftp_app_init(ftp_client: FTP):
    assert ftp_client.pwd() == "/", "Initially in root dir"
    assert ftp_client.nlst() == list(_BLANK_HDD_DRIVES), "Initially in root dir"


@pytest.mark.parametrize("cwd", _BLANK_HDD_DRIVES)
def test_ftp_app_set_cwd_valid(ftp_client: FTP, cwd: str):
    ftp_client.cwd(cwd)
    assert ftp_client.pwd() == "/" + cwd + "/", "Changed directory"
    assert ftp_client.nlst() == [], "Nothing in here!"


@pytest.mark.parametrize("cwd", _BLANK_HDD_DRIVES)
def test_ftp_app_set_cwd_valid(ftp_client: FTP, cwd: str):
    ftp_client.cwd(cwd)
    assert ftp_client.pwd() == "/" + cwd + "/", "Changed directory"
    assert ftp_client.nlst() == [], "Nothing in here!"


def random_string(str_size: int, allowed_chars: str) -> str:
    return "".join(random.choice(allowed_chars) for x in range(str_size))


@pytest.mark.parametrize(
    "dest_filename", ("C/something.bat", "X/test.cpp", "E/test.txt", "F/file.txt")
)
def test_ftp_app_upload_file(ftp_client: FTP, dest_filename: str, tmp_path_factory):
    temp_file_dir = tmp_path_factory.mktemp("files")
    local_filename = os.path.join(temp_file_dir, "local_file.txt")
    with open(local_filename, "w") as local_file:
        allowed_chars = string.ascii_letters + string.punctuation
        str_size = random.randint(1, 100)
        rand_str = random_string(str_size, allowed_chars)
        local_file.write(rand_str)

    with open(local_filename, "rb") as local_file:
        ftp_client.storbinary(f"STOR {dest_filename}", local_file)

    compare_local_to_filename = local_filename + "2"
    with open(compare_local_to_filename, "wb") as compare_local_to_file:
        ftp_client.retrbinary(f"RETR {dest_filename}", compare_local_to_file.write)

    assert (
        open(local_filename).read() == open(compare_local_to_filename).read()
    ), "File uploaded and downloaded successfully"
