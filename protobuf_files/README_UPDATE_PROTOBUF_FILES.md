# Protocol Buffers, Protoc, and Steam:

## About:
Steam uses Google's Protocol Buffer format (aka Protobuf) to send data between systems. Usually, this is between the Steam servers and the Steam Client, but in our case, we're acting like a Steam Client. In order for us to do so, we need to do three things: Get the latest protobuf files (aka `.proto`), compile them to something python understands, then actually use them in the plugin code. Normally, protbuf files are backwards-compatible, so in theory we only need to do this once. However, Steam occasionally changes how they do things (the most notable being the new auth flow introduced in March 2023), so we need the ability to retrieve and update our protobuf definitions and compiled versions. Caution is advised when doing so, however, because Steam can rename or move messages or fields, and while the old calls will work, if you update a proto but don't update the underlying python code, it will error. Usually, however, if you check what's changed in the proto files you'll be fine. 

## Getting started:
1. You must have python 3.7, specifically 3.7.9 or newer. 
2. You must have the modules defined in `requirements/dev.txt` installed. It is highly recommened you set up a virtual environment first. Instructions are part of the regular readme. 

## Getting the latest Proto Files:
The protobuf files that are retrieved from the urls in the `protobuf_steammessages.txt` and `protobuf_webui.txt` files. If Steam moves functions we use, these may need to be updated, but some versions have conflicts so keep that in mind. The instructions are as follows:
1. Make sure your virtual environment has `invoke` installed. if not, install the version in `requirements/app.txt`
2. (Optional) Backup any existing `.proto` files. There may have been breaking changes. While you can view the py files instead to check for changes, it will be much easier to compare the protos instead. 
3. From the main directory, execute one of the following commands
  - `inv PullProtobufSteamMessages` will retrieve the files that (usually) do not conflict with other protobuf files.
  - `inv PullProtobufWebui` will retrieve all protobuf files which stem from the webui definitions. Normally, these require additional protobuf files from the webui, but these conflict with those in steammmessages. To handle this, we currently replace the webui import statements with their steammessages versions, but it's possible this solution will no longer work. Please make sure it does not need anything from those base classes. 
  - `inv PullAllProtobufFiles` will retrieve both the steammessages and webui files. This is the recommended command to use.

## Getting Protoc
In order for us to use the proto files retrieved in the previous part, we need to convert them to python. The tool to do this is called `protoc`. The problem with Protoc is it has occasionally introduced breaking changes, so we need to be careful with what version we used. This is made worse by the fact that python itself is very susceptible to breaking changes, as most modules are third-party and they tend to introduce breaking changes far too often to keep most projects up to date. So, we have provided a tool that gets the version of protoc we use for you and place it in this project. This program is portable in that it won't install anything on your computer, but is also an executable so we don't want to include it in our repo. 
The command is `inv InstallProto`. It makes a folder called `protoc` in the base directory of this project, then retrieves the protoc release for your OS, unzips it, and places it in this folder. You can do this manually if you prefer. If for whatever reason your version is incorrect, you can delete that folder and rerun the command to reinstall it. As of this writing, we use protoc 22.0. Later versions introduce breaking changes and we're not risking it.

## Updating the python files.
Now that we have protoc, we need to actually do the conversion. This process is fairly straightforward:
1. (Optional) Copy all existing files in `src/steam_network/protocol/messages/` to a backup directory. If you did not do this as part of the "Pull" process, do it here. 
2. Run `inv GenerateProtobufMessages`. This will convert all `.proto` files found in the `protobuf_files/proto` directory into their `.py` form. These are placed in the `src/steam_network/protocol/messages` folder.
1. If you made a backup of messages directory, you can compare the files to see if anything changed. `Diff`, `windif`, `winmerge`, or `git diff` can all be useful here. If you did not make a backup, continue to the next step
1. Build the plugin and **thoroughly** check that it works, especially features which may be affected by changes in their protobuf messages. This means checking all cases, not just the simple ones. this is much easier to do if you compare the compiled py files because you can see what changed, and anything unchanged does not need to be checked. 

## Sources

* <https://github.com/steamdatabase/protobufs>
* <https://github.com/ValvePython/steam>
* Uses [BetterProto](https://pypi.org/project/betterproto/) version 1.2.5. There are some manual fixes we have made to clean up the code generated here, but it is mostly the same. 