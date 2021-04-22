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


class DeleteDirectoryParams(NamedTuple):
    """May need to make some directories if we are to be sure that the upload
    was a success
    """

    make_these_directories: Tuple[str, ...]
    create_these_files: Tuple[str, ...]
    delete_this_directory: str


def remove_ftp_dir(ftp: FTP, path: str) -> None:
    """Deletes a directories contents (recursively) before then deletes the
    directory itself
    """
    path = path.rstrip("/")
    print("path:", path)
    lines = []
    ftp.retrlines(f"LIST {path}/", lines.append)
    print("lines:", lines)

    for line in lines:
        components = line.split(" ")
        name = " ".join(components[7:])
        is_dir = components[0][0] == "d"
        print(line, components)
        print(name, is_dir)

        if name in [".", ".."]:
            continue
        elif not is_dir:
            ftp.delete(f"{path}/{name}")
        else:
            remove_ftp_dir(ftp, f"{path}/{name}")

    ftp.rmd(path)


def get_parent_directory_name(path: str) -> str:
    """:returns: the path of the containing directory"""
    return "/".join(path.rstrip("/").split("/")[:-1]) + "/"


@pytest.mark.parametrize(
    "make_these_directories,create_these_files,delete_this_directory",
    (
        DeleteDirectoryParams(("/C/test/",), tuple(), "/C/test"),
        DeleteDirectoryParams(("/C/test/",), ("C/test/file.txt",), "/C/test"),
        DeleteDirectoryParams(
            ("/E/dir/", "/E/otherdir/"), ("E/dir/sd.txt", "E/dir/sd2.bat"), "/E/dir"
        ),
        DeleteDirectoryParams(
            ("/X/test/", "/x/test/test2/"),
            tuple(),
            "/X/test/test2",
        ),
        DeleteDirectoryParams(
            ("/X/test/", "/x/test/test2/"),
            ("X/test/sd.txt", "x/test/test2/sd2.bat"),
            "/X/test/test2",
        ),
    ),
)
def test_delete_directory(
    ftp_client: FTP,
    make_these_directories: Tuple[str, ...],
    create_these_files: Tuple[str, ...],
    delete_this_directory: str,
):
    """Ensure that directories can be deleted and that no other directories or
    files are deleted by mistake
    """
    for directory in make_these_directories:
        ftp_client.mkd(directory)

    for filename in create_these_files:
        ftp_upload_data(ftp_client, "", filename)

    check_this_directory = (
        "/".join(delete_this_directory.rstrip("/").split("/")[:-1]) + "/"
    )

    content_before = ftp_client.nlst(check_this_directory)
    assert (
        delete_this_directory.replace(check_this_directory, "") in content_before
    ), f"directory {delete_this_directory} exists"

    remove_ftp_dir(ftp_client, delete_this_directory)

    assert ftp_client.nlst(check_this_directory) == [
        f
        for f in content_before
        if f != delete_this_directory.replace(check_this_directory, "")
    ], f"directory {delete_this_directory} has been deleted"


class RenameParams(NamedTuple):
    """All data needed to test that a file can be renamed

    This class exists for type checking purposes only
    """

    make_these_directories: Tuple[str, ...]
    create_these_files: Tuple[str, ...]
    old_name: str
    new_name: str


# TODO: test renaming directories
@pytest.mark.parametrize(
    "make_these_directories,create_these_files,old_name,new_name",
    (
        RenameParams(tuple(), ("/C/test",), "/C/test", "/C/test2"),
        RenameParams(tuple(), ("/E/a.cpp",), "/E/a.cpp", "/E/b.py"),
        RenameParams(
            ("/C/somedir/",),
            ("/C/test", "/C/source.c", "/C/somedir/file"),
            "/C/test",
            "/C/test2",
        ),
        RenameParams(
            ("/C/somedir/",),
            ("/C/test", "/C/source.c", "/C/somedir/file"),
            "/C/test",
            "/C/somedir/file.txt",
        ),
        # Moving files across drives seems to not work in the NXDK at the moment :/
        #RenameParams(tuple(), ("/C/test",), "/C/test", "/E/test2"),
        #RenameParams(tuple(), ("/E/some.txt",), "/E/some.txt", "/X/some.bat"),
        # RenameParams(
        #     ("/X/subdir/",), ("/E/some.txt",), "/E/some.txt", "/X/subdir/some.bat"
        # ),
    ),
)
def test_rename(
    ftp_client: FTP,
    make_these_directories: Tuple[str, ...],
    create_these_files: Tuple[str, ...],
    old_name: str,
    new_name: str,
):
    """Ensure that files can be renamed"""
    for directory in make_these_directories:
        ftp_client.mkd(directory)

    for filename in create_these_files:
        ftp_upload_data(ftp_client, "", filename)

    old_file_directory = get_parent_directory_name(old_name)
    old_directory_content_before = ftp_client.nlst(old_file_directory)
    assert (
        old_name.replace(old_file_directory, "") in old_directory_content_before
    ), f"file {old_name} exists in {old_file_directory}"

    new_file_directory = get_parent_directory_name(new_name)
    new_directory_content_before = ftp_client.nlst(new_file_directory)
    assert (
        new_name not in new_directory_content_before
    ), f"{new_name} not originally in {new_file_directory}"

    copying_to_same_dir = old_file_directory == new_file_directory

    ftp_client.rename(old_name, new_name)

    old_directory_content_after = ftp_client.nlst(old_file_directory)
    assert (
        old_name.replace(old_file_directory, "") not in old_directory_content_after
    ), f"file {old_name} no longer in {old_file_directory}"

    assert sorted(ftp_client.nlst(new_file_directory)) == sorted(
        [new_name.replace(new_file_directory, "")]
        + [
            f
            for f in new_directory_content_before
            if not copying_to_same_dir
            or f != old_name.replace(old_file_directory, "")
        ]
    ), f"{old_name} has been renamed to {new_name}"
