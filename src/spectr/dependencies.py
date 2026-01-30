from dataclasses import dataclass


@dataclass(frozen=True)
class AppDependencies:
    broker_api: object
    data_api: object
