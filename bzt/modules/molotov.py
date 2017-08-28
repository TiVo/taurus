"""
Molotov-based executor for Taurus. Python 3.5+ only.

Copyright 2017 BlazeMeter Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import time

from math import ceil
from subprocess import CalledProcessError

from bzt import TaurusConfigError, ToolError
from bzt.engine import ScenarioExecutor, HavingInstallableTools, SelfDiagnosable, FileLister
from bzt.modules.aggregator import ConsolidatingAggregator, ResultsReader
from bzt.modules.console import WidgetProvider, ExecutorWidget
from bzt.utils import shell_exec, shutdown_process, RequiredTool, dehumanize_time


class MolotovExecutor(ScenarioExecutor, FileLister, WidgetProvider, HavingInstallableTools, SelfDiagnosable):
    def __init__(self):
        super(MolotovExecutor, self).__init__()
        self.process = None
        self.report_file_name = None
        self.stdout_file = None
        self.stderr_file = None
        self.tool_path = None
        self.scenario = None

    def _get_script(self):
        scenario = self.get_scenario()
        script = scenario.get("script", TaurusConfigError("You must provide script for Molotov"))
        return self.engine.find_file(script)

    def prepare(self):
        self.tool_path = self.install_required_tools()

        self.stdout_file = open(self.engine.create_artifact("molotov", ".out"), 'w')
        self.stderr_file = open(self.engine.create_artifact("molotov", ".err"), 'w')

        self.report_file_name = self.engine.create_artifact("molotov-report", ".csv")
        # self.reader = None
        # if isinstance(self.engine.aggregator, ConsolidatingAggregator):
        #     self.engine.aggregator.add_underling(self.reader)


    def get_widget(self):
        if not self.widget:
            label = "%s" % self
            self.widget = ExecutorWidget(self, "Molotov: " + label.split('/')[1])
        return self.widget

    def startup(self):
        load = self.get_load()

        cmdline = [self.tool_path]

        if load.concurrency is not None:
            cmdline += ['--workers', str(load.concurrency)]
        # TODO: processes vs workers?
        # TODO: autosizing as `concurrency: auto`?

        duration = 0
        if load.ramp_up:
            ramp_up = int(ceil(dehumanize_time(load.hold)))
            duration += ramp_up
            cmdline += ['--ramp-up', str(ramp_up)]
        if load.hold:
            hold = int(ceil(dehumanize_time(load.hold)))
            duration += hold
        cmdline += ['--duration', str(duration)]

        cmdline += ['--use-extension=bzt.resources.molotov_ext']

        cmdline += [self._get_script()]

        env = {"MOLOTOV_TAURUS_REPORT": self.report_file_name}

        self.start_time = time.time()
        self.process = self.execute(cmdline, stdout=self.stdout_file, stderr=self.stderr_file, env=env)

    def check(self):
        ret_code = self.process.poll()
        if ret_code is None:
            return False
        if ret_code != 0:
            raise ToolError("molotov exited with non-zero code: %s" % ret_code, self.get_error_diagnostics())
        return True

    def shutdown(self):
        shutdown_process(self.process, self.log)

    def post_process(self):
        if self.stdout_file and not self.stdout_file.closed:
            self.stdout_file.close()
        if self.stderr_file and not self.stderr_file.closed:
            self.stderr_file.close()

    def install_required_tools(self):
        # TODO: check for python3 too?
        tool_path = self.settings.get('path', 'molotov')
        tool = Molotov(tool_path, self.log)
        if not tool.check_if_installed():
            tool.install()
        return tool_path

    def get_error_diagnostics(self):
        diagnostics = []
        if self.stdout_file is not None:
            with open(self.stdout_file.name) as fds:
                contents = fds.read().strip()
                if contents.strip():
                    diagnostics.append("molotov STDOUT:\n" + contents)
        if self.stderr_file is not None:
            with open(self.stderr_file.name) as fds:
                contents = fds.read().strip()
                if contents.strip():
                    diagnostics.append("molotov STDERR:\n" + contents)
        return diagnostics

    def resource_files(self):
        return [self._get_script()]


class Molotov(RequiredTool):
    def __init__(self, tool_path, parent_logger):
        super(Molotov, self).__init__("Molotov", tool_path)
        self.tool_path = tool_path
        self.log = parent_logger.getChild(self.__class__.__name__)

    def check_if_installed(self):
        self.log.debug('Checking Molotov: %s' % self.tool_path)
        try:
            shell_exec([self.tool_path, '-h'])
        except (CalledProcessError, OSError):
            return False
        return True

    def install(self):
        raise ToolError("You must install molotov tool to use it")
