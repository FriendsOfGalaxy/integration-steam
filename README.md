# Steam Integration

GOG Galaxy 2.0 Community integration for Steam.

_Table of Contents_

<!-- Generated with [DocToc](https://github.com/thlorenz/doctoc) -->
<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->


- [Open Beta](#open-beta)
  - [Known Issues](#known-issues)
  - [Installation](#installation)
  - [Logging](#logging)
- [Setup (For Developers)](#setup-for-developers)
  - [Environment Setup (Windows)](#environment-setup-windows)
  - [Environment Setup (macOS)](#environment-setup-macos)
- [Making Changes](#making-changes)
- [Testing new Builds (non-developers)](#testing-new-builds-non-developers)
  - [Installation (non-dev, TL;DR)](#installation-non-dev-tldr)
  - [Install Error fixes](#install-error-fixes)
- [Why this fork?](#why-this-fork)
- [Credits](#credits)
  - [Current Version](#current-version)
  - [The names of individual developers will appear here, soon(ish). Any thanks can be directed there](#the-names-of-individual-developers-will-appear-here-soonish-any-thanks-can-be-directed-there)
  - [Original Version](#original-version)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

## Open Beta

This project is in open beta. It is not completely bulletproof, but it has been extensively tested. We are hoping that crowdsourcing the error checking will help find anything we may have missed.

### Known Issues

* Large libraries are known to be a little wonky. Sometimes, the plugin may crash after initially starting it, but then immediately work properly once you hit "retry". There's not much we can do here.
* If you take too long to enter a 2FA code, any login stuff after that have a small chance of crashing. This is because steam kicks us out after roughly a minute of inactivity. We reconnect, but if we were sending them something when they kicked us out, we'd never get a response and after a minute of waiting, the plugin will close. Restarting the plugin will fix this, but it is something we are looking at fixing in a later version. In our tests, it has happened, but is difficult to replicate. If this issue is more prevalent than we anticipate, it's something we will address immediately. 
* Closing GOG immediately after connecting for the first time may cause GOG to crash. Similarly, disconnecting Steam immediately after connecting it may cause the plugin to crash, though you usually can hit retry and it'll work again. Basically, GOG thinks we are immediately done syncing once we connect, and that is not the case, especially for larger libraries. So, it thinks it can disconnect immediately too, and if we're in the middle of writing some data down, it has to wait, but has basically hamstrung us in the process. It's not an ideal situation. Fortunately, it only happens once, and won't happen at all if you give it time.

### Installation

1. Close GOG Galaxy. 
1. Download the `windows.zip` file of the latest version in [the Releases page](https://github.com/ABaumher/galaxy-integration-steam/releases).
1. Navigate to GOG Galaxy steam plugin directory: 
   * Windows:
      ```
      %localappdata%\GOG.com\Galaxy\plugins\installed\steam_ca27391f-2675-49b1-92c0-896d43afa4f8
      ```
   * macOS:
      ```
      ~/Library/Application Support/GOG.com/Galaxy/plugins/installed/steam_ca27391f-2675-49b1-92c0-896d43afa4f8
      ```
1. If the directory does not exist, create it. If it does, delete all its content. 
1. Extract the content of `windows.zip` to that directory. 
1. Start GOG Galaxy. 

### Logging

We tried to kill as many bugs and test as many behaviors as possible, but we aren't perfect.
<br>You may find some case we haven't tested.
<br>Please raise an issue here, and in the comment, attach your logs.
<br>They can be found here: 
* Windows:<br>`%programdata%\GOG.com\Galaxy\logs`
* macOS:  <br>`/Users/Shared/GOG.com/Galaxy/Logs`

We typically only need the `steam_<numbers and letters>.log` file.

## Setup (For Developers)

You will need Python 3.7, and at least Python 3.7.9. If on Windows, you need to use the 32-bit version. You will then need to set up your python virtual environment, and then have `pip` get all the dependencies the project needs in your virtual environment. Once you have that, you can start making changes. Some IDEs will do this for you, but here are explicit instructions for doing it on your own.

### Environment Setup (Windows)

* Python 3.7.9 is the latest available Python 3.7 release you can easily get on Windows. it is available here: [Python 3.7.9 32-bit][Python379]. Please make sure you use the 32-bit version, even on 64-bit machines. If you have a package manager that can get python 3.7, you may also use that.
* If you have another version of python installed, it is highly recommended you install `py` when you go through the installer. Our tools are designed to use `py` if it's available, but fallback to just `python`. When you have multiple versions of python installed, `python` may not refer to 3.7 and that would break the code.
* Create a new virtual env:
	- If you have py, run `py -3.7 -m venv .venv`
	- If you only have python 3.7.9, run `python -m venv .venv`
* Activate the virtual env. Using powershell, run `.venv\Scripts\activate.ps1`
* Install the dev dependencies:<br>
  `pip install -r requirements/dev.txt`

### Environment Setup (macOS)

* Python 3.7.9 is available as a package at [Python 3.7.9 32-bit][Python379]. However, if you have another version of python installed, it is highly recommended you get `pyenv` and install python 3.7 through there. It's likely to be a newer version of python 3.7. 
  - The easiest way to get pyenv is through `Homebrew`. This can be installed from [Homebrew � The Missing Package Manager for macOS (or Linux)](https://brew.sh/)<br/> 
	Then, from terminal, you can run `brew install pyenv`<br/>
	To actually get python 3.7.9, run `pyenv install 3.7.9`. You can also use a newer version of 3.7, like 3.7.16 <br/>
	Finally, tell this project to use python 3.7.x for all python commands from this folder. <br/>
	`pyenv local 3.7.9` or whatever newer version you used.
* Set up the virtual environment. This is the same for pyenv and only python 3.7.9:<br/>
`python -m venv .venv`
* Activate the virtual env:<br/>
  `.venv/Scripts/activate`
* Install the dev dependencies:<br>
  `pip install -r requirements/dev.txt`
* NOTE: macOS requires certifications. We installed certifi, but it typically requires a symlink be added to your certificates, and that's not the case. If you installed the program from the pkg on python's website, it comes bundled with an `Install Certificates.command` that you can run. We have also provided a slimmed-down version of it, but it likely does not have permission to run. 
	- To User our version:<br/>
	`chmod +x "Install Certificates.command"`<br/>
	`./Install Certificates.command` You may need to allow it through gatekeeper. we recommend viewing the script before allowing it if you are uncomfortable with executing our script. It is copied directly from the python 3.7.9 pkg, we just remove the install certifi command (we already did that).

## Making Changes

Once you are set up, you can make whatever changes you need to. There are, however, a few commands we'd like to make you aware of. 

Steam uses protobufs for its messages. Please see README_UPDATE_PROTOBUF_FILES.md in the protobuf_files directory for more information on how these work and how to update them.

There are several commands that make your life easier. These are done via the `invoke` python module. To do so, make sure your virtual environment is active (`.venv\Scripts\activate.ps1` on Windows via cmd/powershell, `.venv/Scripts/activate` on macOS via Terminal) and then the following commands will be available to you:

To build your code, run `inv build`<br/>
To run the defined python tests on your code, run `inv test`<br/>
To install the changed code on your local GOG Galaxy instance, run `inv install`. Note that GOG Galaxy must not be running when you do this.
To pack a zipped release file that you can share with others, run `inv pack`

## Testing new Builds (non-developers)

For some testing, we will require you build to the latest version from scratch. For non-developers, however, the full developer install is overkill, so we've made a simplified version that only does the bare essentials to take the source code and install a plugin from it. There are only a few commands you need to run. If you want to know what they do, they are documented above each command. A tl;dr: version is below it.

Please do the following:
* Download or clone this repo. If you download a zip, make sure to extract it. You need to be in the main directory for this to work. 
* Download [Python 3.7.9 32-bit][Python379]. FOR WINDOWS:
  <br> If you have another version of python installed, make sure `install py` is checked.
  <br> This makes it easier to select which version of python you are using and we need our virtual environment in 3.7.9.
  <br> If using Windows, make sure you have enabled the setting that `adds Python to the PATH environmental variable`.
  <br> These should be the default settings, but make sure anyway.
  <br/> FOR MAC: run `Install Certificates.command`

* Create a new virtual env:
	- If you only have python 3.7.9<br>
	`python -m venv .venv`
	- IF you have multiple python versions installed and are on Windows (assumes you have `py` as well)<br>
	`py -3.7 -m venv .venv`
	- If you are on macOS, you will need to specify which python you are using. Please consult StackOverflow (we're Windows developers, sorry!).
* Activate the virtual env 
  - Windows, Powershell:<br>
  `.venv\Scripts\activate`
  - macOS, terminal:<br>
  `.venv/Scripts/activate`
* Use Pip to get the python tools we need to install the plugin.
<br>These will only be applied to the `.venv` virtual environment you created earlier:<br>
  `pip install -r requirements/install.txt`
* Install the plugin. It should work if you have deleted the original plugin, but will patch it if it is there.<br>
  `inv install`

### Installation (non-dev, TL;DR)

<b>Windows (Powershell recommended)</b>
```
@echo You must have installed python 3.7.9 (32 bit). If not, the rest of this won't work.
py.exe -3.7 -m venv .venv
@echo If the previous command did not work, you do not have py installed or py is not in your PATH.
@echo If you only have python 3.7.9, run the next command.
@echo If it worked, skip the next command.
python.exe -m venv .venv
@echo virtual environment is installed. on to the next step.
.venv\Scripts\activate
pip install -r requirements/install.txt
inv install
```

<b>macOS</b> (assumes your shell is bash, which is the default. if you are good enough to change that, you can figure out how to run these)
```
echo You must have installed python 3.7.9 (macOS). If not, the rest of this won't work.
py -3.7 -m venv .venv
echo If the previous command did not work, you do not have py installed or py is not in your PATH.
echo If you only have python 3.7.9, run the next command.
echo If it worked, skip the next command.
python -m venv .venv
echo virtual environment is installed. on to the next step.
.venv/Scripts/activate
pip install -r requirements/install.txt
inv install
```

### Install Error fixes

If `inv install` throws a bunch of errors, make sure you have the proper python venv set up. It should complain about `getargspec`. If this happens, you created the wrong virtual environment. You can either delete the `.venv` folder and reinstall it, or create a new virtual environment with a different name and use that.

Make sure you use `py -3.7` when creating your venv. If you don't have `py`, get it. You can specify the full path to python 3.7 instead if you want, but that's harder to do and harder to explain here. 

## Why this fork?

Well, without being too complicated, Steam changed how they do authentication. We used to be able to use one call and magically get a lot of info we needed. But, if we're being honest, it was a little insecure, and it easy. While we were using it for legitimate purposes, not everyone else was, and one of Valve's greatest deterrence to botting or DOS attacks (etc) is making things difficult. The new workflow uses a significant back-and-forth between a Steam Server and ourselves, closely resembling a common web form of authentication called OAuth2. This meant a lot of under-the-hood changes. 

## Credits

### Current Version

This is a fork of https://github.com/FriendsOfGalaxy/galaxy-integration-steam

The new Authorization flow implementation is heavily influenced by SteamKit. https://github.com/SteamRE/SteamKit<br>
While we have not utilized their source code, they have implemented the new authentication workflow before we did, and we used their knowledge of how to do so in order to implement it ourselves. If you are doing anything steam related in C#, you should check them out; their project has far more features than our own.

Some work was influenced by ValvePython. https://github.com/ValvePython/steam<br>
Our projects do the same thing, but use different methods (we use asyncio, they use gevent, for example). Both projects were working on the new Auth Flow simultaneously, with little collaboration between us. That said, their scope is much larger than our own and lets you do a lot more things. If you are looking for a python means of implementing a steam network authentication, you should use their work instead.

### The names of individual developers will appear here, soon(ish). Any thanks can be directed there

### Original Version

Original Plugin was based on work and research done by others:
* https://github.com/prncc/steam-scraper
* https://github.com/rhaarm/steam-scraper
* https://github.com/mulhod/steam_reviews
* https://github.com/summersb92/aeolipile
* https://github.com/rcpoison/steam-scraper
* https://github.com/chmccc/steam-scraper


[Python379]: https://www.python.org/downloads/release/python-379/
