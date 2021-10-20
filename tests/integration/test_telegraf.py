import os

import tomli

from buildpack import telegraf
from tests.integration import basetest


class TestCaseTelegraf(basetest.BaseTest):
    def _stage_test_app(self, env=None):
        """Stage a compatible test app for tests with telegraf"""
        # TODO : Update this to 9.7.0 mda
        # TODO : FORCE_ENABLE_MICROMETER_METRICS would eventually be removed
        # once we go live with the micrometer metrics stream.
        if not env:
            env = {"FORCE_ENABLE_MICROMETER_METRICS": "true"}
        self.stage_container(
            "BuildpackTestApp-mx9-6.mda",
            env_vars=env,
        )
        self.start_container()
        # self.assert_app_running()

    def test_telegraf_running(self):
        """Ensure telegraf running when APPMETRICS_TARGET set"""
        self.stage_container(
            "BuildpackTestApp-mx-7-16.mda",
            env_vars={"APPMETRICS_TARGET": '{"url": "https://foo.bar/write"}'},
        )
        self.start_container()
        self.assert_app_running()
        self.assert_listening_on_port(telegraf.get_statsd_port(), "telegraf")
        self.assert_string_not_in_recent_logs("E! [inputs.postgresql]")
        self.assert_string_not_in_recent_logs("E! [processors.")

    def test_telegraf_not_running_runtime_less_than_mx9_7(self):
        """Ensure telegraf is not running for runtimes less than 9.7.0

        Scenario where we have not enabled APPMETRICS_TARGET or Datadog.
        """
        self.stage_container(
            "BuildpackTestApp-mx-7-16.mda",
            env_vars={"FORCE_ENABLE_MICROMETER_METRICS": "true"},
        )
        self.start_container()
        self.assert_app_running()
        self.assert_not_running("[t]elegraf")

    def test_telegraf_running_runtime_greater_than_mx9_7(self):
        """Ensure telegraf is running for runtimes greater than 9.7.0

        Starting runtime version 9.7.0, telegraf is expected to be
        enabled to handle metrics send from micrometer.
        """
        self._stage_test_app()
        self.assert_running("[t]elegraf")

    def test_metrics_registry_greater_than_mx9_7(self):
        """Test metrics registry is set for runtime greater than 9.7."""
        self._stage_test_app()
        self.await_string_in_recent_logs(
            "Metrics: Adding metrics registry InfluxMeterRegistry", max_time=10
        )

    def test_telegraph_config_for_micrometer(self):
        """Ensure telegraf is configured to collect metrics from micrometer"""
        # TODO : Update this to 9.7.0 mda
        version = telegraf.VERSION
        telegraf_config_path = os.path.join(
            os.sep,
            "app",
            ".local",
            "telegraf",
            f"telegraf-{version}",
            "etc",
            "telegraf",
            "telegraf.conf",
        )
        self._stage_test_app(
            env={
                "FORCE_ENABLE_MICROMETER_METRICS": "true",
                "TRENDS_STORAGE_URL": "some-fake-url",
            }
        )

        # Ensure we have the influxdb_listener plugin added
        output = self.run_on_container(
            "cat {} | grep -A2 inputs.influxdb_listener".format(
                telegraf_config_path
            )
        )
        assert output is not None
        assert str(output).find("influxdb_listener") >= 0

        # Ensure we have the appropriate headers
        output = self.run_on_container(
            "cat {} | grep -A5 outputs.http.headers".format(
                telegraf_config_path
            )
        )
        assert output is not None
        assert str(output).find("Micrometer-Metrics") >= 0
