import datetime
from typing import Any, Dict, List, Optional
from manual_test_base import ManualTestBase, handle_command_line, CLEAN_SERVER_RECORD_TYPE, POPULATED_SERVER_RECORD_TYPE
from manual_test.utilities.notification_utilities import NotificationUtilities
from manual_test.utilities.workspace_utilities import WorkspaceUtilities

SERVICE_NAME = 'Alarm'
ALARM_DATABASE_NAME = 'nialarms'
TEST_NAME = 'AlarmMigrationTest'
TEST_WORKSPACE_NAME = f'CustomWorkspaceFor{TEST_NAME}'
ACKNOWLEDGE_ALARMS_BY_ID_ROUTE = 'nialarm/v1/acknowledge-instances-by-instance-id'
ADD_NOTES_TO_ALARM_ROUTE_FORMAT = 'nialarm/v1//instances/{instance_id}/notes'
CREATE_OR_UPDATE_ALARM_ROUTE = 'nialarm/v1/instances'
DELETE_ALARMS_BY_ID_ROUTE = 'nialarm/v1/delete-instances-by-instance-id'
QUERY_ALARMS_ROUTE = 'nialarm/v1/query-instances'

"""Set this when debugging to cleanup the alarm database prior to populating the server with alarms."""
DEBUG_CLEANUP_EXISTING_DATA = False


class TestAlarm(ManualTestBase):

    def populate_data(self) -> None:
        if DEBUG_CLEANUP_EXISTING_DATA:
            self.__delete_existing_alarms()

        WorkspaceUtilities().create_workspace(TEST_WORKSPACE_NAME, self)
        notification_strategy_id = self.__create_test_notification_strategy()
        index = 0
        startTime = datetime.datetime.now()
        for alarm in self.__generate_alarms(startTime, notification_strategy_id):
            instance_id = self.__raise_alarm(alarm)
            self.__add_note(instance_id, startTime + datetime.timedelta(hours=1), index)
            self.__acknowledge_if_needed(alarm, instance_id, startTime + datetime.timedelta(hours=2), index)
            self.__clearIfNeeded(alarm, startTime + datetime.timedelta(hours=3), index)
            index = index + 1

        self.record_data(SERVICE_NAME, ALARM_DATABASE_NAME, POPULATED_SERVER_RECORD_TYPE, self.__get_all_alarms())

    def record_initial_data(self) -> None:
        self.record_data(SERVICE_NAME, ALARM_DATABASE_NAME, CLEAN_SERVER_RECORD_TYPE, self.__get_all_alarms())

    def validate_data(self) -> None:
        source_service_snapshot = self.read_recorded_data(
            SERVICE_NAME,
            ALARM_DATABASE_NAME,
            POPULATED_SERVER_RECORD_TYPE,
            required=True)
        target_service_snaphot = self.read_recorded_data(
            SERVICE_NAME,
            ALARM_DATABASE_NAME,
            CLEAN_SERVER_RECORD_TYPE,
            required=False)
        current_snapshot = self.__get_all_alarms()
        workspaces = WorkspaceUtilities().get_workspaces(self)
        notification_strategies = NotificationUtilities().get_all_notification_strategies(self)

        migrated_record_count = 0
        for alarm in current_snapshot:
            expected_alarm = self.__find_matching_alarm_instance(alarm, source_service_snapshot)
            if expected_alarm is not None:
                self.__assert_alarms_equal(expected_alarm, alarm)
                self.__assert_alarm_has_valid_workspace(alarm, workspaces)
                self.__assert_alarm_has_valid_notification_strategies(alarm, notification_strategies)
                migrated_record_count = migrated_record_count + 1
            else:
                # Verify items that are generated by the target version and not present in the source.
                expected_alarm = self.__find_matching_alarm_id(alarm, target_service_snaphot)
                if expected_alarm is not None:
                    self.__assert_alarms_equal(expected_alarm, alarm)
                    self.__assert_alarm_has_valid_workspace(alarm, workspaces)
                    self.__assert_alarm_has_valid_notification_strategies(alarm, notification_strategies)
                else:
                    displayName = alarm['displayName']
                    print(f'WARNING: Encountered alarm not in the record: {displayName}')

        assert len(source_service_snapshot) == migrated_record_count

    def __get_all_alarms(self):
        query = {
            'workspaces': ['*']
        }
        response = self.post(QUERY_ALARMS_ROUTE, json=query)
        response.raise_for_status()

        return response.json()['filterMatches']

    def __raise_alarm(self, alarm: Dict[str, Any]) -> str:
        response = self.post(CREATE_OR_UPDATE_ALARM_ROUTE, json=alarm)
        response.raise_for_status()
        return response.json()['instanceId']

    def __add_note(self, instance_id: str, time, index: int):
        uri = ADD_NOTES_TO_ALARM_ROUTE_FORMAT.format(instance_id=instance_id)
        note = {
            'note': f'Note #{index}',
            'createdAt': self.datetime_to_string(time)
        }
        response = self.post(uri, json={'notes': [note]})
        response.raise_for_status()

    def __acknowledge_if_needed(
            self,
            alarm: Dict[str, Any],
            instance_id: str,
            time,
            index: int
    ):
        if self.__need_to_acknowledge(alarm):
            ack = {
                'instanceIds': [instance_id],
                'forceClear': False,
                'note': {
                    'note': f'Acknowledgment #{index}',
                    'createdAt': self.datetime_to_string(time)
                }
            }
            response = self.post(ACKNOWLEDGE_ALARMS_BY_ID_ROUTE, json=ack)
            response.raise_for_status()

    def __clearIfNeeded(self, alarm: Dict[str, Any], time, index: int):
        if self.__need_to_clear(alarm):
            clear = {
                'alarmId': alarm['alarmId'],
                'workspace': alarm['workspace'],
                'transition': self.__generate_clear_transition(time, index)
            }
            response = self.post(CREATE_OR_UPDATE_ALARM_ROUTE, json=clear)
            response.raise_for_status()

    def __delete_existing_alarms(self):
        instance_ids = [alarm['instanceId'] for alarm in self.__get_all_alarms()]
        if len(instance_ids) > 0:
            response = self.post(DELETE_ALARMS_BY_ID_ROUTE, json={'instanceIds': instance_ids})
            response.raise_for_status()

    def __create_test_notification_strategy(self) -> str:
        result = NotificationUtilities().create_simple_smtp_notification_strategy(
            self,
            f'Notification strategy for {TEST_NAME}',
            'Test notification strategy')

        return result['notification_strategy']['id']

    def __generate_alarms(self, startTime, notification_strategy_id: str) -> List[Dict[str, Any]]:
        alarms = []
        for workspace_id in WorkspaceUtilities().get_workspaces(self):
            alarms.extend(self.__generate_alarms_for_workspace(workspace_id, startTime, notification_strategy_id))
        return alarms

    def __generate_alarms_for_workspace(
        self,
        workspace_id: str,
        startTime,
        notification_strategy_id: str
    ) -> List[Dict[str, Any]]:
        alarms = []
        alarms.append(self.__generate_alarm(workspace_id, startTime, notification_strategy_id, 0, 'Set'))
        alarms.append(self.__generate_alarm(workspace_id, startTime, notification_strategy_id, 1, 'Set.Ack'))
        alarms.append(self.__generate_alarm(workspace_id, startTime, notification_strategy_id, 2, 'Set.Clear'))
        alarms.append(self.__generate_alarm(workspace_id, startTime, notification_strategy_id, 3, 'Set.Ack.Clear'))
        return alarms

    def __generate_alarm(
            self,
            workspace_id,
            startTime,
            notification_strategy_id: str,
            index: int,
            mode: str
    ) -> Dict[str, Any]:
        channel = f'{TEST_NAME}.{mode}'
        return {
            'alarmId': f'{channel}.{index}',
            'workspace': workspace_id,
            'transition': self.__generate_set_transition(startTime),
            'notificationStrategyIds': [notification_strategy_id],
            'channel': channel,
            'resourceType': f'{TEST_NAME} resource',
            'displayName': f'Test alarm #{index}',
            'description': f'Migration Test alarm - mode:{mode}',
            'keywords': [TEST_NAME],
            'properties': {'forTest': 'True'}
        }

    def __generate_set_transition(self, time) -> Dict[str, Any]:
        return {
            'transitionType': 'SET',
            'occuredAt': self.datetime_to_string(time),
            'severityLevel': 1,
            'condition': 'Test Alarm Set',
            'shortText': 'Alarm created for test',
            'detailText': f'This alarm was created for {TEST_NAME}',
            'keywords': [TEST_NAME],
            'properties': {'forTest': 'True'}
        }

    def __generate_clear_transition(self, time, index: int) -> Dict[str, Any]:
        return {
            'transitionType': 'CLEAR',
            'occuredAt': self.datetime_to_string(time),
            'severityLevel': -1,
            'condition': 'Test Alarm Cleared',
            'shortText': 'Alarm cleared for test',
            'detailText': f'Alarm clear notification #{index}',
            'keywords': [TEST_NAME],
            'properties': {'forTest': 'True'}
        }

    def __need_to_acknowledge(self, alarm: Dict[str, Any]) -> bool:
        return 'Ack' in alarm['alarmId']

    def __need_to_clear(self, alarm: Dict[str, Any]) -> bool:
        return 'Clear' in alarm['alarmId']

    def __assert_alarms_equal(self, expected: Dict[str, Any], actual: Dict[str, Any]):
        if self.__is_test_alarm(expected):
            assert expected == actual
        else:
            # Minimal checks for a alarms we didn't create. We don't know that the state of this alarm
            # hasn't changed since the server started.
            assert expected['channel'] == actual['channel']
            assert expected['resourceType'] == actual['resourceType']
            assert expected['displayName'] == actual['displayName']
            assert expected['description'] == actual['description']
            assert expected['keywords'] == actual['keywords']
            assert expected['properties'] == actual['properties']

    def __assert_alarm_has_valid_workspace(self, alarm: Dict[str, Any], workspaces: List[str]):
        matching_workspace = next((workspace for workspace in workspaces if workspace == alarm['workspace']), None)
        assert matching_workspace is not None

    def __assert_alarm_has_valid_notification_strategies(
        self,
        alarm: Dict[str, Any],
        notification_strategies: List[Dict[str, Any]]
    ):
        if self.__is_test_alarm(alarm):
            assert len(alarm['notificationStrategyIds']) > 0

        for strategy_id in alarm['notificationStrategyIds']:
            matching_strategies = (strategy for strategy in notification_strategies if strategy['id'] == strategy_id)
            assert next(matching_strategies, None) is not None

    def __is_test_alarm(self, alarm: Dict[str, Any]) -> bool:
        return 'forTest' in alarm['properties']

    def __find_matching_alarm_instance(
        self,
        record: Dict[str, Any],
        collection: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        return self.find_record_with_matching_property_value(record, collection, 'instanceId')

    def __find_matching_alarm_id(
        self,
        record: Dict[str, Any],
        collection: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        return self.find_record_with_matching_property_value(record, collection, 'alarmId')


if __name__ == '__main__':
    handle_command_line(TestAlarm)
