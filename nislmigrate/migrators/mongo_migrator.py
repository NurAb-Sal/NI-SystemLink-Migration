"""Handle Mongo operations."""

import os
import subprocess
import sys
from types import SimpleNamespace
from typing import Dict

from bson.codec_options import CodecOptions
from bson.binary import UUID_SUBTYPE
from pymongo import errors as mongo_errors
from pymongo import MongoClient

from nislmigrate import constants
from nislmigrate.migration_action import MigrationAction

MONGO_DATABASE_NAME_CONFIGURATION_KEY = "Mongo.Database"
MONGO_PORT_NAME_CONFIGURATION_KEY = "Mongo.Port"
MONGO_USER_CONFIGURATION_KEY = "Mongo.User"
MONGO_PASSWORD_CONFIGURATION_KEY = "Mongo.Password"
MONGO_CUSTOM_CONNECTION_STRING_CONFIGURATION_KEY = "Mongo.CustomConnectionString"

NI_DIRECTORY = os.path.join(os.environ.get("ProgramW6432"), "National Instruments")
SKYLINE_DIRECTORY = os.path.join(NI_DIRECTORY, "Shared", "Skyline")
NO_SQL_DATABASE_SERVICE_DIRECTORY = os.path.join(SKYLINE_DIRECTORY, "NoSqlDatabase")
MONGO_EXECUTABLES_DIRECTORY = os.path.join(NO_SQL_DATABASE_SERVICE_DIRECTORY, "bin")
MONGO_DUMP_EXECUTABLE_PATH = os.path.join(MONGO_EXECUTABLES_DIRECTORY, "mongodump.exe")
MONGO_RESTORE_EXECUTABLE_PATH = os.path.join(MONGO_EXECUTABLES_DIRECTORY, "mongorestore.exe")
MONGO_EXECUTABLE_PATH = os.path.join(MONGO_EXECUTABLES_DIRECTORY, "mongod.exe")
MONGO_CONFIGURATION_PATH = os.path.join(NO_SQL_DATABASE_SERVICE_DIRECTORY, "mongodb.conf")


class MongoMigrator:
    is_mongo_process_running = False
    mongo_process_handle = None

    def __del__(self):
        self.__stop_mongo()

    def __start_mongo(self):
        """
        Begins the mongo DB subprocess on this computer.
        :return: The started subprocess handling mongo DB.
        """
        if not self.is_mongo_process_running:
            self.mongo_process_handle = subprocess.Popen(
                MONGO_EXECUTABLE_PATH + " --config " + '"' + MONGO_CONFIGURATION_PATH + '"',
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                env=os.environ,
            )
            self.is_mongo_process_running = True

    def __stop_mongo(self):
        """
        Stops the mongo process.
        :return: None.
        """
        if self.is_mongo_process_running:
            subprocess.Popen.kill(self.mongo_process_handle)
            self.is_mongo_process_running = False

    def __get_mongo_connection_arguments(self,
                                         service_config: Dict[str, str],
                                         action: MigrationAction):
        if MONGO_CUSTOM_CONNECTION_STRING_CONFIGURATION_KEY in service_config:
            connection_string = service_config[MONGO_CUSTOM_CONNECTION_STRING_CONFIGURATION_KEY]
            mongo_database_name = service_config[MONGO_DATABASE_NAME_CONFIGURATION_KEY]
            arguments = "--uri {0}".format(connection_string)
            arguments += self.__fix_mongo_restore_bug(action, mongo_database_name)
            return arguments
        return "--port {0} --db {1} --username {2} --password {3}".format(
            str(service_config[MONGO_PORT_NAME_CONFIGURATION_KEY]),
            service_config[MONGO_DATABASE_NAME_CONFIGURATION_KEY],
            service_config[MONGO_USER_CONFIGURATION_KEY],
            service_config[MONGO_PASSWORD_CONFIGURATION_KEY],)

    def __fix_mongo_restore_bug(self, action: MigrationAction, mongo_database_name: str):
        # We need to provide the db option (even though it's redundant with the uri)
        # because of a bug with mongoDB 4.2
        # https://docs.mongodb.com/v4.2/reference/program/mongorestore/#cmdoption-mongorestore-uri
        return " --db " + mongo_database_name if action == MigrationAction.RESTORE else ""

    def capture_migration(self, mongo_config: Dict, migration_directory: str):
        """
        Capture the data in mongoDB from the given service.
        :param mongo_config: The mongo configuration for a service.
        :param migration_directory: The directory to migrate the service in to.
        """
        connection_arguments = self.__get_mongo_connection_arguments(mongo_config,
                                                                     MigrationAction.CAPTURE)
        mongo_dump_command = MONGO_DUMP_EXECUTABLE_PATH + " "
        mongo_dump_command += connection_arguments + " "
        mongo_dump_command += "--out %s " % migration_directory
        mongo_dump_command += "--gzip"
        self.__ensure_mongo_process_is_running_and_execute_command(mongo_dump_command)

    def restore_migration(self, mongo_config: Dict, migration_directory: str):
        """
        Restore the data in mongoDB from the given service.

        :param service: The service to capture the data for.
        :param migration_directory: The directory to restore the service in to.
        :return: None.
        """
        collection_name = mongo_config[MONGO_DATABASE_NAME_CONFIGURATION_KEY]
        mongo_dump_file = os.path.join(migration_directory, collection_name)
        if not os.path.exists(mongo_dump_file):
            raise FileNotFoundError("Could not find the captured service at " + mongo_dump_file)
        connection_arguments = self.__get_mongo_connection_arguments(mongo_config,
                                                                     MigrationAction.RESTORE)
        mongo_restore_command = MONGO_RESTORE_EXECUTABLE_PATH + " "
        mongo_restore_command += connection_arguments + " "
        mongo_restore_command += "--gzip " + mongo_dump_file
        self.__ensure_mongo_process_is_running_and_execute_command(mongo_restore_command)

    def migrate_document(self, destination_collection, document):
        """
        Inserts a document into a collection.

        :param destination_collection: The collection to migrate the document to.
        :param document: The document to migrate.
        :return: None.
        """
        try:
            print("Migrating " + str(document["_id"]))
            destination_collection.insert_one(document)
        except mongo_errors.DuplicateKeyError:
            print("Document " + str(document["_id"]) + " already exists. Skipping")

    def identify_metadata_conflict(self, destination_collection, source_document):
        """
        Gets any conflicts that would occur if adding source_document to a document collection.

        :param destination_collection: The collection to see if there are conflicts in.
        :param source_document: The document to test if it conflicts.
        :return: The conflicts, if there are any.
        """
        destination_query = {
            "$and": [
                {"workspace": source_document["workspace"]},
                {"path": source_document["path"]},
            ]
        }
        destination_document = destination_collection.find_one(destination_query)
        if destination_document:
            return SimpleNamespace(
                **{
                    "source_id": source_document["_id"],
                    "destination_id": destination_document["_id"],
                }
            )

        return None

    def merge_history_document(self, source_id, destination_id, destination_db):
        """
        Merges the contents of one document into another document.

        :param source_id: The document to merge from.
        :param destination_id: The document to merge in to.
        :param destination_db: The database to merge the history document in.
        :return: None.
        """
        destination_collection = destination_db.get_collection("values")
        destination_collection.update_one(
            {"metadataId": source_id}, {"$set": {"metadataId": destination_id}}
        )

    def migrate_metadata_collection(self, source_db, destination_db):
        """
        Migrates a collection with the name "metadata" from the source database
        to the destination database.

        :param source_db: The database to migrate from.
        :param destination_db: The database to migrate to.
        :return: None.
        """
        collection_name = "metadata"
        source_collection = source_db.get_collection(collection_name)
        source_collection_iterable = source_collection.find()
        destination_collection = destination_db.get_collection(collection_name)
        for source_document in source_collection_iterable:
            conflict = self.identify_metadata_conflict(destination_collection, source_document)
            if conflict:
                message = "Conflict Found! " + "source_id=" + str(conflict.source_id)
                message += " destination_id=" + str(conflict.destination_id)
                print(message)

                source_id = conflict.source_id
                destination_id = conflict.destination_id
                self.merge_history_document(source_id, destination_id, destination_db)
            else:
                self.migrate_document(destination_collection, source_document)

    def migrate_values_collection(self, source_db, destination_db):
        """
        Migrates a collection with the name "values" from the source database
        to the destination database.

        :param source_db: The database to migrate from.
        :param destination_db: The database to migrate to.
        :return: None.
        """
        collection_name = "values"
        collection_iterable = source_db.get_collection(collection_name).find()
        destination_collection = destination_db.get_collection(collection_name)
        for document in collection_iterable:
            self.migrate_document(destination_collection, document)

    def check_merge_history_readiness(self, destination_db):
        """
        Checks whether a database is ready for data to be migrated to it.
        :param destination_db: The database to check and see if it is ready
                               for data to be migrated into it.
        """
        # look for fields that should be set when Org modeling is present.
        # If they are missing exit.
        collection_name = "metadata"
        destination_collection = destination_db.get_collection(collection_name)
        if destination_collection.find({"workspace": {"$exists": False}}).count() > 0:
            print(
                "Database is not ready for migration. Update the connection string in "
                "C:\\ProgramData\\National Instruments\\Skyline\\Config\\TagHistorian.json to "
                "point to the nitaghistorian database in your MongoDB instance and restart Service"
                " Manager. Please see <TODO: DOCUMENTATION LINK HERE> for more detail"
            )
            sys.exit()

    def migrate_within_instance(self, service):
        """
        Migrates the data for a service from one mongo database to another mongo database.

        :param service: The service to migrate.
        """
        codec = CodecOptions(uuid_representation=UUID_SUBTYPE)
        config = service.config
        client = MongoClient(
            host=[config[constants.no_sql.name]["Mongo.Host"]],
            port=config[constants.no_sql.name]["Mongo.Port"],
            username=config[constants.no_sql.name]["Mongo.User"],
            password=config[constants.no_sql.name]["Mongo.Password"],
        )
        source_db = client.get_database(name=service.SOURCE_DB, codec_options=codec)
        destination_db = client.get_database(name=service.destination_db, codec_options=codec)
        self.check_merge_history_readiness(destination_db)
        self.migrate_values_collection(source_db, destination_db)
        self.migrate_metadata_collection(source_db, destination_db)

    def migrate_mongo_cmd(self, service, action: MigrationAction, migration_directory: str):
        """
        Performs a restore or a capture operation depending on the chosen action.

        :param service: The service to capture or restore.
        :param action: Whether to capture or restore.
        :param migration_directory: Directory to capture into or capture from.
        """
        if action == constants.thdbbug.arg:
            self.migrate_within_instance(service)
        if action == MigrationAction.CAPTURE:
            self.capture_migration(service, migration_directory)
        if action == MigrationAction.RESTORE:
            self.restore_migration(service, migration_directory)

    def __ensure_mongo_process_is_running_and_execute_command(self, command: str):
        self.__start_mongo()
        subprocess.run(command, check=True)