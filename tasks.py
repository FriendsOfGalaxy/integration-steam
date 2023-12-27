import os
import sys
import json
import requests
import tempfile
import zipfile
from shutil import rmtree, copy2, which
from distutils.dir_util import copy_tree
from io import BytesIO

from urllib.request import urlopen #used to retrieve the proto files from github.
from http.client import HTTPResponse

from invoke import task
from galaxy.tools import zip_folder_to_file

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PROTOC_DIR = os.path.join(BASE_DIR, "protoc")

with open(os.path.join(BASE_DIR, "src", "manifest.json"), "r") as f:
    MANIFEST = json.load(f)

if sys.platform == 'win32':
    DIST_DIR = os.environ['localappdata'] + '\\GOG.com\\Galaxy\\plugins\\installed'
    PLATFORM = "win32"
    
    if which("py"):
        PYTHON_EXE = "py -3.7"
    else:
        PYTHON_EXE = "python"

    PROTOC_EXE = os.path.join(PROTOC_DIR, "bin", "protoc.exe")
    PROTOC_INCLUDE_DIR = os.path.join(PROTOC_DIR, "include")
    PROTOC_DOWNLOAD_URL = "https://github.com/protocolbuffers/protobuf/releases/download/v3.19.4/protoc-3.19.4-win32.zip"

elif sys.platform == 'darwin':
    DIST_DIR = os.path.realpath(os.path.expanduser("~/Library/Application Support/GOG.com/Galaxy/plugins/installed"))
    PLATFORM = "macosx_10_13_x86_64"  # @see https://github.com/FriendsOfGalaxy/galaxy-integrations-updater/blob/master/scripts.py
    PYTHON_EXE = "python"

    PROTOC_EXE = os.path.join(PROTOC_DIR, "bin", "protoc")
    PROTOC_INCLUDE_DIR = os.path.join(PROTOC_DIR, "include")
    PROTOC_DOWNLOAD_URL = "https://github.com/protocolbuffers/protobuf/releases/download/v3.19.4/protoc-3.19.4-osx-x86_64.zip"


@task
def build(c, output='output', ziparchive=None):
    if os.path.exists(output):
        print('--> Removing {} directory'.format(output))
        rmtree(output)

    # Firstly dependencies need to be "flattened" with pip-compile,
    # as pip requires --no-deps if --platform is used.
    print('--> Flattening dependencies to temporary requirements file')
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
        c.run(f'pip-compile requirements/app.txt --output-file=-', out_stream=tmp)

    # Then install all stuff with pip to output folder
    print('--> Installing with pip for specific version')
    args = [
        'pip', 'install',
        '-r', tmp.name,
        '--python-version', '37',
        '--platform', PLATFORM,
        '--target "{}"'.format(output),
        '--no-compile',
        '--no-deps'
    ]
    c.run(" ".join(args), echo=True)
    os.unlink(tmp.name)

    print('--> Copying source files')
    copy_tree("src", output)

    if ziparchive is not None:
        print('--> Compressing to {}'.format(ziparchive))
        zip_folder_to_file(output, ziparchive)

def _read_url(response :HTTPResponse) -> str:
    charset = response.headers.get_content_charset('utf-8')
    raw_data = response.read()
    return raw_data.decode(charset)


def _get_filename_from_url(url: str) -> str:
    return url.split("/")[-1]


def _pull_protobufs_internal(c, selection: str, silent: bool = False):
    target_dir = os.path.join(BASE_DIR, "protobuf_files", "proto")
    list_file = os.path.join(BASE_DIR, "protobuf_files", f"protobuf_{selection}.txt")

    try:
        rmtree(target_dir)
    except Exception:
        pass  # directory probably just already exists

    os.makedirs(target_dir, exist_ok=True)

    with open(list_file, "r") as file:
        urls = filter(None, file.read().split("\n"))  # filter(None, ...) is used to strip empty lines from the collection

    for url in urls:
        if not silent:
            print("Retrieving: " + url)

        file_name = _get_filename_from_url(url)

        response = urlopen(url)
        data = _read_url(response)

        # needed to avoid packages of the form ...steam_auth.steamclient_pb2
        if ".steamclient.proto" in file_name:
            file_name = file_name.replace(".steamclient.proto", ".proto")
        if ".steamclient.proto" in data:
            data = data.replace(".steamclient.proto", ".proto")

        if "cc_generic_services" in data:
            data = data.replace("cc_generic_services", "py_generic_services")

        if selection == "webui":
            # lil' hack to avoid name collisions; the definitions are (almost) identical so this shouldn't break anything
            data = data.replace("common_base.proto", "steammessages_unified_base.proto")
            data = data.replace("common.proto", "steammessages_base.proto")

        # force proto2 syntax if not yet enforced
        if "proto2" not in data:
            data = f'syntax = "proto2";\n' + data

        with open(os.path.join(target_dir, file_name), "w") as dest:
            dest.write(data)


@task
def InstallProtoc(c):
    if os.path.exists(PROTOC_DIR) and os.path.isdir(PROTOC_DIR):
        print("protoc directory already exists, remove it if you want to reinstall protoc")
        return

    os.makedirs(PROTOC_DIR)

    resp = requests.get(PROTOC_DOWNLOAD_URL, stream=True)
    resp.raise_for_status()

    with zipfile.PyZipFile(BytesIO(resp.content)) as zipf:
        zipf.extractall(PROTOC_DIR)

    print("protoc successfully installed")


#for whatever reason if i give this an _ in the name it can't find it. i have no idea why. so TitleCase
@task
def PullProtobufSteamMessages(c, silent=False):
   _pull_protobufs_internal(c, "steammessages", silent)

@task
def PullProtobufWebui(c, silent=False):
   _pull_protobufs_internal(c, "webui", silent)

@task
def PullAllProtobufFiles(c, silent=False):
    PullProtobufSteamMessages(c, silent)
    PullProtobufWebui(c, silent)

@task
def ClearProtobufFiles(c):
    filelist = [ f for f in os.listdir("protobuf_files/proto") if f.endswith(".proto") ]
    for f in filelist:
        os.remove(os.path.join("protobuf_files/proto", f))



@task
def GenerateProtobufMessages(c):
    proto_files_dir = os.path.join(BASE_DIR, "protobuf_files", "proto")

    out_dir = os.path.join(BASE_DIR, "src", "steam_network", "protocol", "messages")

    try:
        rmtree(os.path.join(out_dir))
    except Exception:
        pass  # directory probably just didn't exist

    os.makedirs(os.path.join(out_dir), exist_ok=True)

    # make sure __init__.py is there
    with open(os.path.join(out_dir, "__init__.py"), "wb") as fp:
        fp.write(b"")

    all_files = " ".join(map(lambda x: '"' + os.path.join(proto_files_dir, x) + '"', os.listdir(proto_files_dir)))
    print(f'{PROTOC_EXE} -I "{proto_files_dir}" --python_out="{out_dir}" {all_files}')
    c.run(f'{PROTOC_EXE} -I "{proto_files_dir}" --python_out="{out_dir}" {all_files}')


@task
def ClearGeneratedProtobufs(c, genFile = True):
    out_dir = "./protobuf_files/gen/" if genFile else "src/steam_network/protocol/messages"
    filelist = [ f for f in os.listdir(out_dir) if f.endswith(".py") ]
    for f in filelist:
        os.remove(os.path.join(out_dir, f))

@task
def test(c):
    c.run('pytest')


@task
def install(c):
    dist_path = os.path.join(DIST_DIR, "steam_" + MANIFEST['guid'])
    build(c, output=dist_path)


@task
def pack(c):
    output = "steam_" + MANIFEST['guid']
    build(c, output=output, ziparchive='steam_v{}.zip'.format(MANIFEST['version']))
    rmtree(output)
