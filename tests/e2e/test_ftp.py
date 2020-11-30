"""Test the basic functions of the FTP client

Currently only tests whatever is needed for pyxboxtest.

Note: all of these tests just use a blank HDD as the starting point as
internally pyxboxtest uses this FTP app to create HDDs with extra content
"""
from ftplib import FTP, error_perm
from io import BytesIO
import random
import string
from typing import List, NamedTuple, Tuple
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


@pytest.fixture(scope="session")
def og_xbox_ftp_iso() -> str:
    """:returns: the location of the OG Xbox FTP ISO"""
    repo = git.Repo(".", search_parent_directories=True)
    return os.path.join(repo.working_tree_dir, "OGXboxFTP.iso")


@pytest.fixture
def ftp_app(og_xbox_ftp_iso: str, xqemu_blank_hdd_template: XQEMUHDDTemplate):
    """Fixture that gives an instance of XQEMU with a blank HDD running OG
    Xbox FTP
    """
    with XQEMUXboxAppRunner(
        hdd_filename=xqemu_blank_hdd_template.create_fresh_hdd(),
        dvd_filename=og_xbox_ftp_iso,
    ) as app:
        yield app


@pytest.fixture
def ftp_client(ftp_app: XQEMUXboxAppRunner):
    """Fixture that gives an ftp client connected to an instance of OG Xbox
    FTP
    """
    yield ftp_app.get_ftp_client("xbox", "xbox")


def test_ftp_app_init(ftp_client: FTP):
    """Ensures that initial conditions of the FTP server are correct by
    checking that we are in the root directory and that we can see all the HDD
    partitions
    """
    assert ftp_client.pwd() == "/", "Initially in root dir"
    assert ftp_client.nlst() == list(_BLANK_HDD_DRIVES), "Initially in root dir"


@pytest.mark.parametrize("cwd", (x for x in _BLANK_HDD_DRIVES if x != "F"))
def test_ftp_app_set_cwd_valid(ftp_client: FTP, cwd: str):
    """Sets a valid current working directory"""
    ftp_client.cwd(cwd)
    assert ftp_client.pwd() == "/" + cwd + "/", "Changed directory"
    assert ftp_client.nlst() == [], "Nothing in here!"


@pytest.mark.parametrize("cwd", ("lol", "thing", "test"))
def test_ftp_app_set_cwd_invalid(ftp_client: FTP, cwd: str):
    """Sets an invalid current working directory"""
    with pytest.raises(error_perm):
        ftp_client.cwd(cwd)
    assert ftp_client.pwd() == "/", "Not changed directory"


def create_random_string() -> str:
    """Gives us some random string"""
    allowed_chars = string.ascii_letters + string.punctuation
    str_size = random.randint(1, 100)
    rand_str = r"".join(random.choice(allowed_chars) for x in range(str_size))

    return rand_str


def ftp_upload_data(ftp_client: FTP, data: str, remote_filename: str) -> None:
    """Uploads the given string as a file to the FTP server"""
    data_reader = BytesIO(data.encode("utf8"))
    ftp_client.storbinary(f"STOR {remote_filename}", data_reader)


def ftp_get_file_content(ftp_client: FTP, remote_filename: str) -> str:
    """:returns: the contents of a file from the FTP server"""
    data = BytesIO()
    ftp_client.retrbinary(f"RETR {remote_filename}", data.write)
    data.seek(0)
    return data.read().decode("utf8")


def ftp_generate_and_upload_random_files(
    ftp_client: FTP, remote_filenames: Tuple[str]
) -> List[str]:
    """Generates random text files and uploads them via FTP.
    :param remote_filenames: the filenames for the randomly generated files. \
        One file is generated per name
    :returns: the contents of the files that were uploaded
    """
    file_contents = []
    for remote_filename in remote_filenames:
        random_string = create_random_string()
        file_contents.append(random_string)
        ftp_upload_data(ftp_client, random_string, remote_filename)

    return file_contents


def ftp_assert_files_have_contents(
    ftp_client, file_contents: List[str], remote_filenames: Tuple[str]
) -> None:
    """Check that the files on the FTP server have the right content"""
    for i, remote_filename in enumerate(remote_filenames):
        assert file_contents[i] == ftp_get_file_content(
            ftp_client, remote_filename
        ), "File downloaded successfully"


@pytest.mark.parametrize(
    "remote_filenames",
    (
        ("C/thing.bat",),
        ("C/tst.txt", "Y/other.bat"),
        # ("F/tst.txt",),
        ("C/something.bat", "X/test.cpp", "E/test.txt"),
    ),
)
def test_ftp_app_upload_download_data(
    og_xbox_ftp_iso: str,
    remote_filenames: Tuple[str],
    xqemu_blank_hdd_template: XQEMUHDDTemplate,
):
    """Uploads random files (one for each filename) and then downloads them
    and compares the contents to what was uploaded to ensure that they were
    uploaded correctly.

    After this the FTP is shutdown a second instance is started to repeat the
    download and compare operation to make sure that the files were actually
    stored on the HDD and not just in memory.
    """
    hdd_filename = xqemu_blank_hdd_template.create_fresh_hdd()

    with XQEMUXboxAppRunner(
        hdd_filename=hdd_filename, dvd_filename=og_xbox_ftp_iso
    ) as app:
        ftp = app.get_ftp_client("xbox", "xbox")
        file_contents = ftp_generate_and_upload_random_files(ftp, remote_filenames)

        # Files uploaded successfully
        ftp_assert_files_have_contents(ftp, file_contents, remote_filenames)

    # Create a new app to test that they are actually stored on the HDD and not
    # just in memory
    with XQEMUXboxAppRunner(
        hdd_filename=hdd_filename, dvd_filename=og_xbox_ftp_iso
    ) as app:
        ftp_assert_files_have_contents(
            app.get_ftp_client("xbox", "xbox"), file_contents, remote_filenames
        )


class ListDirectoryParams(NamedTuple):
    """Parameters used by tests for listing a directory"""

    list_directory: str
    expected_content: Tuple[str, ...]


class MakeDirectoryParams(NamedTuple):
    """Parameters used by the tests for making a directory with some content"""

    make_these_directories: Tuple[str, ...]
    create_these_files: Tuple[str, ...]
    run_these_list_tests: Tuple[ListDirectoryParams, ...]


@pytest.mark.parametrize(
    "make_these_directories,create_these_files,run_these_list_tests",
    (
        MakeDirectoryParams(
            ("C/test", "C/other"),
            tuple(),
            (ListDirectoryParams("/C/", ("test", "other")),),
        ),
        MakeDirectoryParams(
            ("C/test", "C/test/other"),
            ("E/test.txt", "C/test/other/file"),
            (
                ListDirectoryParams("/C/", ("test",)),
                ListDirectoryParams("/C/test/", ("other",)),
                ListDirectoryParams("/C/test/other/", ("file",)),
                ListDirectoryParams("/E/", ("test.txt",)),
            ),
        ),
        MakeDirectoryParams(
            ("C/test", "C/other"),
            ("C/file1", "C/other/file2"),
            (
                ListDirectoryParams("/C/", ("test", "other", "file1")),
                ListDirectoryParams("/C/other/", ("file2",)),
            ),
        ),
    ),
)
def test_make_and_list_directory(
    ftp_client: FTP,
    make_these_directories: Tuple[str, ...],
    create_these_files: Tuple[str, ...],
    run_these_list_tests: Tuple[ListDirectoryParams, ...],
):
    """Ensures that we can make directories and see them"""
    for directory in make_these_directories:
        ftp_client.mkd(directory)

    for filename in create_these_files:
        ftp_upload_data(ftp_client, "", filename)

    for list_test_to_run in run_these_list_tests:
        assert (
            tuple(ftp_client.nlst(list_test_to_run.list_directory))
            == list_test_to_run.expected_content
        )


class DeleteFileParams(NamedTuple):
    """May need to make some directories if we are to be sure that the upload
    was a success
    """

    make_these_directories: Tuple[str, ...]
    create_these_files: Tuple[str, ...]
    check_this_directory: str


@pytest.mark.parametrize(
    "make_these_directories,create_these_files,check_this_directory",
    (
        DeleteFileParams(tuple(), ("C/test.txt",), "/C/"),
        DeleteFileParams(tuple(), ("E/test2.txt",), "/E/"),
        DeleteFileParams(
            ("X/dir", "X/dir/dir2"), ("X/dir/dir2/test2.txt",), "/X/dir/dir2/"
        ),
        DeleteFileParams(
            tuple(),
            (
                "C/test.txt",
                "C/test2.txt",
                "C/test3.txt",
            ),
            "/C/",
        ),
        DeleteFileParams(
            tuple(),
            (
                "E/test2.txt",
                "E/somethingelse.bat",
            ),
            "/E/",
        ),
        DeleteFileParams(
            ("X/dir", "X/dir/dir2"),
            (
                "X/dir/dir2/asdasd.asd",
                "X/dir/dir2/dd.ss",
                "X/dir/dir2/something.xbe",
                "X/dir/dir2/noext",
            ),
            "/X/dir/dir2/",
        ),
    ),
)
def test_delete_file(
    ftp_client: FTP,
    make_these_directories: Tuple[str, ...],
    create_these_files: Tuple[str, ...],
    check_this_directory: str,
):
    """Ensure that files can be deleted and that no other files are deleted by
    mistake
    """
    for directory in make_these_directories:
        ftp_client.mkd(directory)

    for filename in create_these_files:
        ftp_upload_data(ftp_client, "", filename)

    file_to_delete = random.choice(create_these_files)

    assert (
        tuple(
            check_this_directory.lstrip("/") + filename
            for filename in ftp_client.nlst(check_this_directory)
        )
        == create_these_files
    ), "files exist"

    ftp_client.delete(file_to_delete)

    assert ftp_client.nlst(check_this_directory) == [
        file.split("/")[-1] for file in create_these_files if file != file_to_delete
    ], f"only {file_to_delete} has been deleted"
