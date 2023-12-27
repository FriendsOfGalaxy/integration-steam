__version__ = "1.2.1"
__changelog__ = {
    "unreleased": '''
    ''',
    "1.0.7": """
    - Fixes issues when SteamGuard is disabled. Made it so 2FA codes would ignore leading or trailing whitespace.
    - Code cleanup
    """,
    "1.0.6": """
    - reintroduces password santization so users with long passwords or illegal characters can log in as intended
    - Code cleanup
    """,
    "1.0.5": """
    - implemented a temporary fix to make the receive loop only send off a few jobs before stopping to receive a message, instead of doing all the jobs at once.
    """,
    "1.0.4": """
    - refreshed python generated protobuf files
    - removed public profiles `backend`. The new auth flow makes it irrelevant.
    - implemented new auth flow.
    """,
    "1.0.2": """
    - refreshed python generated protobuf files
    - handle eresult 48: `TryWithDifferentCM` on every login attempt
    - fix timeout problems when importing bigger libraries (#129 thanks @nbrochu!)
    - amend and cleanup authentication process error handling so that it gives immediate feedback
    - add some unit tests for achievement parser + refactor
    - fix some unit tests for storing plugin version on which user logged in and test for default backend switch
    """,
    "1.0.1": """
    - added browser window for handling external error during checking profile's privacy
    - added browser window for case when user has private game details or has no games
    - fixed an issue with plugin incorrectly reporting the steam profile as private (or "Incorrect Steam64 ID")
      if a game with for example ";" in its title is owned
    """,
    "1.0.0": '''
    - refactor high-level code to support multi-backend architecture
    - add `fallback backend` functionality in case the `initial backend` loses connection
    - add PublicProfiles `backend` that rely on publicly visible user data
    - add user configuration at `../steam_plugin_config.ini`
      (default: SteamNetwork as `initial backend` and PublicProfiles as a `fallback backend`)
      NOTE: plugin reconnection is required to use fallback functionality
    ''',
    "0.60": '''
    - add html fixes
    - add css visual fixes
    - handle eresult 48: `TryWithDifferentCM` and similar cases to blacklist a server temporarily
    ''',
    "0.59": '''
    - fix not showing installed games due to changed Steam libraryfolders.vdf format (#122 thanks @tfredett and all from #121!)
    ''',
    "0.58": '''
    - handle not established/broken websockets connection during getting obfuscated IP
    - fix all achievements import stuck on 0% when having old version achievements unlocked e.g. in Train Simulator (#114 thanks @Tauron93!)
    - translate eresult 5 (`EResult.InvalidPassword`) to `InvalidCredentials` instead of `BackendError` on login key authorization (#103 thanks @SparrowBrain!)
      this change should cause "Connection Lost" in Galaxy instead of plugin going "Offline" disposing of need for further plugin reconnection
    - remove old code leftovers from backend.py
    ''',
    "0.57": '''
    - add helper script for injecting Nethook (for devs)
    - improved login auth protobuf message for following attributes: client_package_version, machine_id, client_language, qos_level, machine_name, client_os_type
    ''',
    "0.56": '''
    - fix handling if libraryfolders.vdf was not found
    - connection stability improvement (no longer connects to servers from different regions) (#108 thanks @SparrowBrain!)
    ''',
    "0.55": '''
    - add obfuscated_private_ip to ClientLogOn message (#104 thanks @SparrowBrain!)
      this change should fix losing authentication in case of multiple machines in the same network (eresult 32 and eresult 5)
    ''',
    "0.54": '''
    - fix common problem with not showing achievements (Steam messages > 1MB) (#100 thanks @Neverous!)
    - fix typo in EMsg.ClientLoggedOff listener
    - rename "subscription" name from `Family Sharing` to `Steam Family Sharing`
    - remove old deprecated code for http logging path
    ''',
    "0.53": '''
    - fix crashes due to pushing big cache multiple times in a row
    - fix crashes due to O(n^2) licenses lookup for big libraries
    - fix crashes due to apps parsing for big libraries
    - workaround issue with improper games cache invalidation for big libraries
    - improved how Steam in/out protobuf traffic is logged
    ''',
    "0.52": '''
    - raise BackendError instead of BackendTimeout when couldn't login with token
    - register steam app ticket with CM before logging and save a new ticket after login
    ''',
    "0.51.2": '''
    - Enhance local game sizes by returning downloading size if game is not fully installed yet
    - Drop attaching obfuscated private ip to login params.
    ''',
    "0.51.1": '''
    - Fixup marking when games cache is ready in situations when part of the cache was already initialized
    - Optimize retrieving subscription status
    - Fixes for rich presence translations for certain games (dota, stellaris)
    ''',
    "0.51": '''
    - Use package access token when retrieving package information, should fix some games not appearing
    ''',
    "0.50.9": '''
    - Refactor games cache for readability and debugging purposses
    - Implement getting local game sizes
    ''',
    "0.50.8": '''
    - Fix crash on potential looping rich presence translation
    - Fix possible 0 owned games sent issue occuring if previous retrieval was stopped mid-way
    ''',
    "0.50.7": '''
    - Use LoginKeyAccepted message post auth
    - Retry using servers from a different cellid (update login params to handle cell id)
    ''',
    "0.50.6": '''
    - Send log off call on plugin shutdown
    - More precise login parameters, up protocol version
    ''',
    "0.50.5": '''
    - Don't get stuck on broken cache in subsequent runs, instead always reimport packages which didn't end up being resolved (Thanks Dugsdghk!)
    - Don't crash protobuf on bytes response in initial rich presence parsing (Thanks Dugsdghk!)
    ''',
    "0.50.4": '''
    - Fix for owned games which are also present in one of family sharings being reported only as family shared. (Thanks for the help Svill and TM-CG!)
    ''',
    "0.50.3": '''
    - Dont endlessly retry auth to not lock user out
    ''',
    "0.50.2": '''
    - Fix missing achievement_id crashing protobuf_client (Thanks MartinCa!)
    - Extended supported result codes from steam auth
    - Increase logging of protobuf responses
    ''',
    "0.50.1": '''
    - Ignore incompatible cache
    ''',
    "0.50": '''
    - Handle potential infinite rich presence translation
    - Return Family sharing games as a subscriptions
    - Dont crash on unknown presence format
    ''',
    "0.49": '''
    - Better handle parsing rich presence from steam
    - Add a cooldown to parsing local files, should fix ssues with large cpu usage during game installation
    - Better flow in case of clicking forgot password during auth ( focus should stay on proper window )
    ''',
    "0.48": '''
    - Cache the results of owned games so the import is possibly immediate in subsequent plugin runs
    ''',
    "0.47": '''
    - Change the logic of sent friend nicknames to always display the username with optional given nickname instead of one of the two
    - Pull steam friends from protobuf communication instead of scrapping website
    - Move authentication to protobuf
    ''',
    "0.46.5": '''
    - Hotfix for some achievements not being properly recognized by Galaxy (Trailing whitespace in names)
    ''',
    "0.46": '''
    - Potential fixes for key error on achievements retrieval
    - Retrieve last_played time from protobuf instead of website scrapping
    ''',
    "0.45": '''
    - Quickfix for plugin crash while getting achievements
    - Restore mechanism to get last_played time if game was launched via Steam
    ''',
    "0.44": '''
    - Achievements and GameTime are now pulled from protobufs instead of scrapping the website
    - Tags are now pulled from protobufs instead of scrapping local files (allows for tags import without installed steam client)
    '''
}
