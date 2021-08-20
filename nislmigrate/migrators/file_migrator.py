"""Handle file and directory operations."""

import os
import shutil
import stat
from distutils import dir_util

from nislmigrate import constants
from nislmigrate.migration_action import MigrationAction


class FileMigrator:
    """
    Handles operations that act on the real file system.
    """
    def remove_readonly(self, func, path):
        """
        Removes the readonly attribute from a file path.

        :param func: A continuation to run with the path.
        :param path: The path to remove the readonly attribute from.
        :return: None.
        """
        os.chmod(path, stat.S_IWRITE)
        func(path)

    def determine_migration_directory_for_service(self,
                                                  migration_directory_root: str,
                                                  service_name: str):
        """
        Generates the migration directory for a particular service.

        :param service_name: The name of the service to determine the migration directory for.
        :return: The migration directory for the service.
        """
        return os.path.join(migration_directory_root, service_name)

    def migration_dir_exists(self, dir_):
        """
        Determines whether a directory exists.

        :param dir_: The directory path to check.
        :return: True if the given directory path is a directory and exists.
        """
        return os.path.isdir(dir_)

    def does_file_exist(self,
                        migration_directory: str,
                        file_name: str):
        """
        Checks whether the migrated data for a given single file migration
        service exists in the migration directory and can be restored.

        :param service: The service to verify data has been migrated for.
        :return: True if there is migrated data for a given service
        """
        path = os.path.join(migration_directory, file_name)
        return os.path.isfile(path)

    def service_restore_dir_exists(self,
                                   migration_directory_root: str,
                                   service_name: str):
        """
        Checks whether the migrated data for a given directory migration
        service exists in the migration directory and can be restored.

        :param migration_directory_root: The root directory migration is taking place from.
        :param service: The service to verify data has been migrated for.
        :return: True if there is migrated data for a given service.
        """
        root = migration_directory_root
        migration_directory = self.determine_migration_directory_for_service(self,
                                                                             root,
                                                                             service_name)
        return os.path.isdir(migration_directory)

    def remove_dir(self, dir_):
        """
        Deletes the given directory and its children.

        :param dir_: The directory to remove.
        :return: None.
        """
        if os.path.isdir(dir_):
            shutil.rmtree(dir_, onerror=self.remove_readonly)

    def migrate_singlefile(self,
                           migration_directory_root: str,
                           service_name: str,
                           single_file_source_directory: str,
                           single_file_name: str,
                           action: MigrationAction):
        """
        Perform a capture or restore the given service.

        :param migration_directory_root: The root directory migration is taking place from.
        :param action: Whether to capture or restore.
        :return: None.
        """
        root = migration_directory_root
        migration_dir = self.determine_migration_directory_for_service(root, service_name)
        if action == MigrationAction.CAPTURE:
            self.remove_dir(migration_dir)
            os.mkdir(migration_dir)
            singlefile_full_path = os.path.join(
                constants.program_data_dir,
                single_file_source_directory,
                single_file_name,
            )
            shutil.copy(singlefile_full_path, migration_dir)
        elif action == MigrationAction.RESTORE:
            singlefile_full_path = os.path.join(migration_dir, single_file_name)
            shutil.copy(singlefile_full_path, single_file_source_directory)

    def capture_singlefile(self,
                           migration_directory_root: str,
                           service_name: str,
                           restore_directory: str,
                           file: str):
        root = migration_directory_root
        migration_dir = self.determine_migration_directory_for_service(root, service_name)
        self.remove_dir(migration_dir)
        os.mkdir(migration_dir)
        singlefile_full_path = os.path.join(
            constants.program_data_dir,
            restore_directory,
            file,
        )
        shutil.copy(singlefile_full_path, migration_dir)

    def restore_singlefile(self,
                           migration_directory_root: str,
                           service_name: str,
                           restore_directory: str,
                           file: str) -> None:
        root = migration_directory_root
        migration_dir = self.determine_migration_directory_for_service(root, service_name)
        singlefile_full_path = os.path.join(migration_dir, file)
        shutil.copy(singlefile_full_path, restore_directory)

    def migrate_dir(self,
                    migration_directory_root: str,
                    service_name: str,
                    source_directory: str,
                    action: MigrationAction):
        """
        Perform a capture or restore the given service.

        :param migration_directory_root: The root directory migration is taking place from.
        :param service_name: The name of the service.
        :param action: Whether to capture or restore.
        :return: None.
        """
        root = migration_directory_root
        migration_dir = self.determine_migration_directory_for_service(root, service_name)
        if action == MigrationAction.CAPTURE:
            self.remove_dir(migration_dir)
            shutil.copytree(source_directory, migration_dir)
        elif action == MigrationAction.RESTORE:
            self.remove_dir(source_directory)
            dir_util.copy_tree(migration_dir, source_directory)