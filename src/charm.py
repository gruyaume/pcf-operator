#!/usr/bin/env python3
# Copyright 2022 Guillaume Belanger
# See LICENSE file for licensing details.

"""Charmed operator for the 5G PCF service."""

import logging
from ipaddress import IPv4Address
from subprocess import check_output
from typing import Dict, Optional, Union

from charms.data_platform_libs.v0.data_interfaces import DatabaseCreatedEvent, DatabaseRequires
from charms.nrf_operator.v0.nrf import NRFAvailableEvent, NRFRequires
from charms.observability_libs.v1.kubernetes_service_patch import KubernetesServicePatch
from jinja2 import Environment, FileSystemLoader
from lightkube.models.core_v1 import ServicePort
from ops.charm import CharmBase, PebbleReadyEvent
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)

BASE_CONFIG_PATH = "/etc/pcf"
CONFIG_FILE_NAME = "pcfcfg.conf"
DATABASE_NAME = "free5gc"


class PCFOperatorCharm(CharmBase):
    """Main class to describe juju event handling for the 5G PCF operator."""

    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = self._service_name = "pcf"
        self._container = self.unit.get_container(self._container_name)
        self._database = DatabaseRequires(
            self, relation_name="database", database_name=DATABASE_NAME
        )
        self._nrf_requires = NRFRequires(charm=self, relationship_name="nrf")
        self.framework.observe(self.on.pcf_pebble_ready, self._on_pcf_pebble_ready)
        self.framework.observe(self.on.database_relation_joined, self._on_pcf_pebble_ready)
        self.framework.observe(self._database.on.database_created, self._on_database_created)
        self.framework.observe(self._nrf_requires.on.nrf_available, self._on_nrf_available)

        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[
                ServicePort(name="sbi", port=29507),
            ],
        )

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        """Handle database created event."""
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        if not self._nrf_relation_is_created:
            self.unit.status = BlockedStatus("Waiting for NRF relation to be created")
            event.defer()
            return
        if not self._nrf_data_is_available:
            self.unit.status = WaitingStatus("Waiting for NRF data to be available")
            event.defer()
            return
        self._write_config_file(
            default_database_url=event.uris.split(",")[0],
            nrf_url=self._nrf_requires.get_nrf_url(),
        )
        self._on_pcf_pebble_ready(event)

    def _on_nrf_available(self, event: NRFAvailableEvent) -> None:
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        if not self._database_relation_is_created:
            self.unit.status = BlockedStatus("Waiting for database relation to be created")
            event.defer()
            return
        if not self._database_is_available:
            self.unit.status = WaitingStatus("Waiting for database to be available")
            event.defer()
            return
        self._write_config_file(
            default_database_url=self._database_data["uris"].split(",")[0], nrf_url=event.url
        )
        self._on_pcf_pebble_ready(event)

    def _write_config_file(self, default_database_url: str, nrf_url: str) -> None:
        jinja2_environment = Environment(loader=FileSystemLoader("src/templates/"))
        template = jinja2_environment.get_template("pcfcfg.conf.j2")
        content = template.render(
            nrf_url=nrf_url,
            pcf_hostname=self._pcf_hostname,
            database_name=DATABASE_NAME,
            database_url=default_database_url,
        )
        self._container.push(path=f"{BASE_CONFIG_PATH}/{CONFIG_FILE_NAME}", source=content)
        logger.info(f"Pushed {CONFIG_FILE_NAME} config file")

    @property
    def _nrf_data_is_available(self) -> bool:
        """Returns whether the NRF data is available.

        Returns:
            bool: Whether the NRF data is available.
        """
        if not self._nrf_requires.get_nrf_url():
            return False
        return True

    @property
    def _database_is_available(self) -> bool:
        """Returns whether the database is available.

        Returns:
            bool: Whether the database is available.
        """
        return self._database.is_resource_created()

    @property
    def _database_data(self) -> Dict:
        """Returns the database data.

        Returns:
            Dict: The database data.
        """
        if not self._database_is_available:
            raise RuntimeError("Database is not available")
        return self._database.fetch_relation_data()[self._database.relations[0].id]

    @property
    def _config_file_is_written(self) -> bool:
        if not self._container.exists(f"{BASE_CONFIG_PATH}/{CONFIG_FILE_NAME}"):
            logger.info(f"Config file is not written: {CONFIG_FILE_NAME}")
            return False
        logger.info("Config file is written")
        return True

    def _on_pcf_pebble_ready(
        self, event: Union[PebbleReadyEvent, DatabaseCreatedEvent, NRFAvailableEvent]
    ) -> None:
        if not self._database_relation_is_created:
            self.unit.status = BlockedStatus("Waiting for database relation to be created")
            return
        if not self._nrf_relation_is_created:
            self.unit.status = BlockedStatus("Waiting for NRF relation to be created")
            return
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        if not self._config_file_is_written:
            self.unit.status = WaitingStatus("Waiting for config file to be written")
            return
        self._container.add_layer("pcf", self._pebble_layer, combine=True)
        self._container.replan()
        self.unit.status = ActiveStatus()

    @property
    def _database_relation_is_created(self) -> bool:
        return self._relation_created("database")

    @property
    def _nrf_relation_is_created(self) -> bool:
        return self._relation_created("nrf")

    def _relation_created(self, relation_name: str) -> bool:
        """Returns whether a given Juju relation was crated.

        Args:
            relation_name (str): Relation name

        Returns:
            str: Whether the relation was created.
        """
        if not self.model.get_relation(relation_name):
            return False
        return True

    @property
    def _pebble_layer(self) -> Layer:
        """Returns pebble layer for the charm.

        Returns:
            Layer: Pebble Layer
        """
        return Layer(
            {
                "summary": "pcf layer",
                "description": "pebble config layer for pcf",
                "services": {
                    "pcf": {
                        "override": "replace",
                        "startup": "enabled",
                        "command": f"./pcf --pcfcfg {BASE_CONFIG_PATH}/{CONFIG_FILE_NAME}",
                        "environment": self._environment_variables,
                    },
                },
            }
        )

    @property
    def _environment_variables(self) -> dict:
        return {
            "GRPC_GO_LOG_VERBOSITY_LEVEL": "99",
            "GRPC_GO_LOG_SEVERITY_LEVEL": "info",
            "GRPC_TRACE": "all",
            "GRPC_VERBOSITY": "debug",
            "POD_IP": str(self._pod_ip),
            "MANAGED_BY_CONFIG_POD": "true",
        }

    @property
    def _pod_ip(self) -> Optional[IPv4Address]:
        """Get the IP address of the Kubernetes pod."""
        return IPv4Address(check_output(["unit-get", "private-address"]).decode().strip())

    @property
    def _pcf_hostname(self) -> str:
        return f"{self.model.app.name}.{self.model.name}.svc.cluster.local"


if __name__ == "__main__":
    main(PCFOperatorCharm)
