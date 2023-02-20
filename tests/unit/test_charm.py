# Copyright 2022 Guillaume Belanger
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, patch

from ops import testing
from ops.model import ActiveStatus

from charm import PCFOperatorCharm


class TestCharm(unittest.TestCase):
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports: None,
    )
    def setUp(self):
        self.namespace = "whatever"
        self.harness = testing.Harness(PCFOperatorCharm)
        self.harness.set_model_name(name=self.namespace)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def _nrf_is_available(self) -> str:
        nrf_url = "http://1.1.1.1"
        nrf_relation_id = self.harness.add_relation("nrf", "nrf-operator")
        self.harness.add_relation_unit(
            relation_id=nrf_relation_id, remote_unit_name="nrf-operator/0"
        )
        self.harness.update_relation_data(
            relation_id=nrf_relation_id, app_or_unit="nrf-operator", key_values={"url": nrf_url}
        )
        return nrf_url

    def _database_is_available(self) -> str:
        database_url = "http://6.6.6.6"
        database_username = "banana"
        database_password = "pizza"
        database_relation_id = self.harness.add_relation("database", "mongodb")
        self.harness.add_relation_unit(
            relation_id=database_relation_id, remote_unit_name="mongodb/0"
        )
        self.harness.update_relation_data(
            relation_id=database_relation_id,
            app_or_unit="mongodb",
            key_values={
                "username": database_username,
                "password": database_password,
                "uris": "".join([database_url]),
            },
        )
        return database_url

    @patch("ops.model.Container.push")
    def test_given_nrf_is_available_when_database_is_created_then_config_file_is_written(
        self,
        patch_push,
    ):
        database_url_0 = "1.2.3.4:1234"
        database_url_1 = "5.6.7.8:1111"
        pcf_hostname = f"pcf-operator.{self.namespace}.svc.cluster.local"
        self.harness.set_can_connect(container="pcf", val=True)

        nrf_url = self._nrf_is_available()

        self.harness.charm._on_database_created(
            event=Mock(uris="".join([database_url_0, ",", database_url_1]))
        )

        patch_push.assert_called_with(
            path="/etc/pcf/pcfcfg.conf",
            source=f'configuration:\n  defaultBdtRefId: BdtPolicyId-\n  mongodb:\n    name: free5gc\n    url: { database_url_0 }\n  nrfUri: { nrf_url }\n  pcfName: PCF\n  plmnList:\n  - plmnId:\n      mcc: "208"\n      mnc: "93"\n  - plmnId:\n      mcc: "333"\n      mnc: "88"\n  sbi:\n    bindingIPv4: 0.0.0.0\n    port: 29507\n    registerIPv4: { pcf_hostname }\n    scheme: http\n  serviceList:\n  - serviceName: npcf-am-policy-control\n  - serviceName: npcf-smpolicycontrol\n    suppFeat: 3fff\n  - serviceName: npcf-bdtpolicycontrol\n  - serviceName: npcf-policyauthorization\n    suppFeat: 3\n  - serviceName: npcf-eventexposure\n  - serviceName: npcf-ue-policy-control\ninfo:\n  description: PCF initial local configuration\n  version: 1.0.0\nlogger:\n  AMF:\n    ReportCaller: false\n    debugLevel: info\n  AUSF:\n    ReportCaller: false\n    debugLevel: info\n  Aper:\n    ReportCaller: false\n    debugLevel: info\n  CommonConsumerTest:\n    ReportCaller: false\n    debugLevel: info\n  FSM:\n    ReportCaller: false\n    debugLevel: info\n  MongoDBLibrary:\n    ReportCaller: false\n    debugLevel: info\n  N3IWF:\n    ReportCaller: false\n    debugLevel: info\n  NAS:\n    ReportCaller: false\n    debugLevel: info\n  NGAP:\n    ReportCaller: false\n    debugLevel: info\n  NRF:\n    ReportCaller: false\n    debugLevel: info\n  NamfComm:\n    ReportCaller: false\n    debugLevel: info\n  NamfEventExposure:\n    ReportCaller: false\n    debugLevel: info\n  NsmfPDUSession:\n    ReportCaller: false\n    debugLevel: info\n  NudrDataRepository:\n    ReportCaller: false\n    debugLevel: info\n  OpenApi:\n    ReportCaller: false\n    debugLevel: info\n  PCF:\n    ReportCaller: false\n    debugLevel: info\n  PFCP:\n    ReportCaller: false\n    debugLevel: info\n  PathUtil:\n    ReportCaller: false\n    debugLevel: info\n  SMF:\n    ReportCaller: false\n    debugLevel: info\n  UDM:\n    ReportCaller: false\n    debugLevel: info\n  UDR:\n    ReportCaller: false\n    debugLevel: info\n  WEBUI:\n    ReportCaller: false\n    debugLevel: info',  # noqa: E501
        )

    @patch("ops.model.Container.push")
    def test_given_database_is_available_when_nrf_is_available_then_config_file_is_written(
        self,
        patch_push,
    ):
        nrf_url = "2.2.2.2"
        pcf_hostname = f"pcf-operator.{self.namespace}.svc.cluster.local"

        self.harness.set_can_connect(container="pcf", val=True)
        database_url_0 = self._database_is_available()

        self.harness.charm._on_nrf_available(event=Mock(url=nrf_url))

        patch_push.assert_called_with(
            path="/etc/pcf/pcfcfg.conf",
            source=f'configuration:\n  defaultBdtRefId: BdtPolicyId-\n  mongodb:\n    name: free5gc\n    url: { database_url_0 }\n  nrfUri: { nrf_url }\n  pcfName: PCF\n  plmnList:\n  - plmnId:\n      mcc: "208"\n      mnc: "93"\n  - plmnId:\n      mcc: "333"\n      mnc: "88"\n  sbi:\n    bindingIPv4: 0.0.0.0\n    port: 29507\n    registerIPv4: { pcf_hostname }\n    scheme: http\n  serviceList:\n  - serviceName: npcf-am-policy-control\n  - serviceName: npcf-smpolicycontrol\n    suppFeat: 3fff\n  - serviceName: npcf-bdtpolicycontrol\n  - serviceName: npcf-policyauthorization\n    suppFeat: 3\n  - serviceName: npcf-eventexposure\n  - serviceName: npcf-ue-policy-control\ninfo:\n  description: PCF initial local configuration\n  version: 1.0.0\nlogger:\n  AMF:\n    ReportCaller: false\n    debugLevel: info\n  AUSF:\n    ReportCaller: false\n    debugLevel: info\n  Aper:\n    ReportCaller: false\n    debugLevel: info\n  CommonConsumerTest:\n    ReportCaller: false\n    debugLevel: info\n  FSM:\n    ReportCaller: false\n    debugLevel: info\n  MongoDBLibrary:\n    ReportCaller: false\n    debugLevel: info\n  N3IWF:\n    ReportCaller: false\n    debugLevel: info\n  NAS:\n    ReportCaller: false\n    debugLevel: info\n  NGAP:\n    ReportCaller: false\n    debugLevel: info\n  NRF:\n    ReportCaller: false\n    debugLevel: info\n  NamfComm:\n    ReportCaller: false\n    debugLevel: info\n  NamfEventExposure:\n    ReportCaller: false\n    debugLevel: info\n  NsmfPDUSession:\n    ReportCaller: false\n    debugLevel: info\n  NudrDataRepository:\n    ReportCaller: false\n    debugLevel: info\n  OpenApi:\n    ReportCaller: false\n    debugLevel: info\n  PCF:\n    ReportCaller: false\n    debugLevel: info\n  PFCP:\n    ReportCaller: false\n    debugLevel: info\n  PathUtil:\n    ReportCaller: false\n    debugLevel: info\n  SMF:\n    ReportCaller: false\n    debugLevel: info\n  UDM:\n    ReportCaller: false\n    debugLevel: info\n  UDR:\n    ReportCaller: false\n    debugLevel: info\n  WEBUI:\n    ReportCaller: false\n    debugLevel: info',
        )

    @patch("charm.check_output")
    @patch("ops.model.Container.exists")
    def test_given_config_file_is_written_when_pebble_ready_then_pebble_plan_is_applied(
        self,
        patch_exists,
        patch_check_output,
    ):
        pod_ip = "1.1.1.1"
        patch_exists.return_value = True
        patch_check_output.return_value = pod_ip.encode()

        self._database_is_available()
        self._nrf_is_available()

        self.harness.container_pebble_ready(container_name="pcf")

        expected_plan = {
            "services": {
                "pcf": {
                    "override": "replace",
                    "command": "./pcf --pcfcfg /etc/pcf/pcfcfg.conf",
                    "startup": "enabled",
                    "environment": {
                        "GRPC_GO_LOG_VERBOSITY_LEVEL": "99",
                        "GRPC_GO_LOG_SEVERITY_LEVEL": "info",
                        "GRPC_TRACE": "all",
                        "GRPC_VERBOSITY": "debug",
                        "POD_IP": pod_ip,
                        "MANAGED_BY_CONFIG_POD": "true",
                    },
                }
            },
        }

        updated_plan = self.harness.get_container_pebble_plan("pcf").to_dict()

        self.assertEqual(expected_plan, updated_plan)

    @patch("charm.check_output")
    @patch("ops.model.Container.exists")
    def test_given_config_file_is_written_when_pebble_ready_then_status_is_active(
        self, patch_exists, patch_check_output
    ):
        patch_exists.return_value = True
        patch_check_output.return_value = b"1.2.3.4"

        self._database_is_available()
        self._nrf_is_available()

        self.harness.container_pebble_ready("pcf")

        self.assertEqual(self.harness.model.unit.status, ActiveStatus())
