import abc
from typing import Callable, Set, Union, Optional
from functools import partial

from galaxy.api.consts import Feature
from galaxy.api.types import Authentication, NextStep
from galaxy.api.plugin import Plugin

class BackendInterface(abc.ABC):
    POSSIBLE_FEATURES = {
        Feature.ImportOwnedGames: "get_owned_games",
        Feature.ImportAchievements: "get_unlocked_achievements",
        Feature.ImportGameTime: "get_game_time",
        Feature.ImportFriends: "get_friends",
        Feature.ImportGameLibrarySettings: "get_game_library_settings",
        Feature.ImportUserPresence: "get_user_presence",
        Feature.ImportSubscriptions: "get_subscriptions",
        Feature.ImportSubscriptionGames: "get_subscription_games",
    }
    PREPARE_CONTEXT_METHODS = {
        "prepare_achievements_context": Feature.ImportAchievements,
        "prepare_game_times_context": Feature.ImportGameTime,
        "prepare_game_library_settings_context": Feature.ImportGameLibrarySettings,
        "prepare_user_presence_context": Feature.ImportUserPresence,
        "prepare_subscription_games_context": Feature.ImportSubscriptionGames,
        "prepare_local_size_context": Feature.ImportLocalSize,
        "prepare_os_compatibility_context": Feature.ImportOSCompatibility,
    }

    @classmethod
    def features(cls) -> Set[Feature]:
        return {
            feat
            for feat, method in cls.POSSIBLE_FEATURES.items()
            if method in cls.__dict__
        }

    @abc.abstractmethod
    async def authenticate(self, stored_credentials=None) -> Union[Authentication, NextStep]:
        pass

    @abc.abstractmethod
    async def pass_login_credentials(self, deprecated:str, credentials, cookies):
        pass

    @abc.abstractmethod
    def tick(self):
        pass

    def __getattr__(self, name: str):
        feature: Optional[Feature] = self.PREPARE_CONTEXT_METHODS.get(name)
        if feature and feature not in self.features():
            raise NotImplementedError(f"{feature} is not implemented in {self.__class__.__name__}")

        if self._is_plugin_public_attr(name):
            return self._getattr_inherited_from_plugin(name)

        raise AttributeError(name)

    @staticmethod
    def _is_plugin_public_attr(name: str):
        return not name.startswith("_") and hasattr(Plugin, name)

    def _getattr_inherited_from_plugin(self, name: str):
        return partial(getattr(Plugin, name), self)
