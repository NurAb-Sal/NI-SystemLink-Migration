# NI-SystemLink-Migration tool `nislmigrate`
`nislmigrate` is a command line utility for migration, backup, and restore of supported SystemLink services.

### Prerequisites
#### 1. SystemLink
- This tool officially supports migration between SystemLink versions 21.0, 21.1, 21.3, & 21.5. Other versions have not been tested.
- **We assume the server you are migrating to is clean with no data. Migrating to a server with existing data will result in data loss.**
- Services that are supported with any caveats and exceptions are detailed in the **Supported Services** section below.
- This tool assumes a single-box SystemLink installation.
- This tool must be run on the same machines as the SystemLink installations.
#### 2. Python
- This tool requires [Python 3.8](https://www.python.org/downloads/release/python-3811/) to run.
- The documentation in this repository assumes Python has been added to your [**PATH**](https://datatofish.com/add-python-to-windows-path/).
### Installation
The latest released version of the tool can be installed by running:
```bash
pip install nislmigrate
```
# Usage
### Backup

To backup the data for a service listed in the **Supported Services** section run the tool with elevated permissions and use the `capture` option with the corresponding flag for each of the services you want to back up (e.g. `--security`):
```bash
nislmigrate capture --security
```
This will backup the data corresponding with each service into the default migration directory (`C:\Users\[user]\Documents\migration\`). You can specify a different migration directory using the `--dir [path]` option:
```bash
nislmigrate capture --security --dir C:\custom-backup-location
```
To backup the data for all supported services at once, the `--all` flag can be used instead of listing out each individual service. Using `--all` will require that you include the `--secret` flag for services that require encrypting backed up data for security:
```bash
nislmigrate capture --all --secret <password>
```

### Restore

> :warning: Restoring requires the `--force` flag to explicitly allow overwriting the existing data on the server. Without it, the command will fail.

To restore the data for a service listed in the **Supported Services** section run the tool with elevated permissions and  use the `restore` option with the corresponding flag for each of the services you want to restore (e.g. `--security`):
```bash
nislmigrate restore --security
```
This will restore the data corresponding with each service from the default migration directory (`C:\Users\[user]\Documents\migration\`). If your captured data is in a different directory that can be specified with the `--dir [path]` option:
```bash
nislmigrate restore --security --dir C:\custom-backup-location
```
To restore the data for all supported services at once, the `--all` flag can be used instead of listing out each individual service. Using `--all` will require that you include the `--secret` flag for services that require encrypting backed up data for security:
```bash
nislmigrate restore --all --secret <password>
```

### Modify

To modify entries in the database in-place without doing a restore run the tool with elevated permissions and use the `modify` option. `modify` currently only works to modify the `--files` service database entries.

Using `modify` with any other migrators (i.e. `--tags`) will no do anything.

#### Updating after moving files

After moving the storage location of the files uploaded to the Files service the database will need to be updated to reflect the new location. The `--files-change-file-store-root` argument can be used for this, either as part of a `restore` operation or in-place as part of a `modify` operation. When used with `restore` the old root location is inferred from the database. When used with `modify` the old root location must be specified with the `--files-file-store-root` argument.

> :warning: `modify` will modify the database directly. A backup of the database should be taken before any modifications using `nislmigrate capture --files --files-metadata-only`

To modify the files root location after moving the files to a new drive:
```bash
cp -r -f C:\old\file\store X:\new\file\store
nislmigrate modify --files --files-change-file-store-root X:\new\file\store --files-file-store-root C:\old\file\store
```

To modify the files root location after moving the files to an S3 bucket:
```bash
aws s3 sync C:\old\file\store s3://my-systemlink-bucket/my-files
nislmigrate modify --files --files-change-file-store-root s3://my-systemlink-bucket/my-files --files-file-store-root C:\old\file\store --files-switch-to-forward-slashes
```

### Migration
>:warning: Server B must be a clean SystemLink installation, any existing data will be deleted.

To migrate from one SystemLink server instance (`server A`) to a different instance (`server B`):
1. Install the migration tool on `server A` and `server B`.
2. Follow the backup instructions to backup the data from `server A`.
3. Copy the data produced by the backup of `server A` on `server B`.
4. **_Warning:_** Ensure `server B` is a clean SystemLink installation, any existing data will be deleted.
5. Follow the restore instructions to restore the backed up data onto `server B`.

# Development
See `CONTRIBUTING.MD` for detailed instructions on developing, testing, and releasing the tool.

# Supported Services
The services that can be migrated with this utility along with short descriptions can be listed by running:
```bash
nislmigrate capture -h
```

Most services require migrating the `--security` service at the same time for the migration to be successful, and some services have additional dependencies which are listed in the table below.  

| **Supported Service**                     | **Argument Flag** | **Also requires migrating** | **Additional Notes**                                                                                                                                                                                                                                                                                                                                                                             |
|---------------------------------|-------------------|-----------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Security                        | `--security`      |                             |                                                                                                                                                                                                                                                                                                                                                                                                  |
| User Data                       | `--userdata`      | `--security`                |                                                                                                                                                                                                                                                                                                                                                                                                  |
| Notifications                   | `--notification`  | `--security`                |                                                                                                                                                                                                                                                                                                                                                                                                  |
| File Ingestion                  | `--files`         | `--security`                | - Must migrate file to the same storage location on the new System Link server.<br>- To capture/restore only the database but not the files themselves, use `--files --files-metadata-only`. This could be useful if, for example, files are stored on a file server with separate backup.<br>- If files are stored in Amazon Simple Storage Service (S3), use `--files --files-metadata-only`.<br>- If the file store path is different on the server you are restoring to, use the `--files-change-file-store-root [NEW_ROOT]` flag to update the metadata of all files to point to the new root during a restore operation.<br>- If you have uploaded your local files to S3 and need to update the file path metadata, use `--files-change-file-store-root [S3://<bucket-name>/<folder-path-if-applicable>]` along with `--files-switch-to-forward-slashes`.  |
| Repository                      | `--repo`          | `--security`                | - Feeds may require additional updates if servers used for migration have different domain names                                                                                                                                                                                                                                                                                                 |
| Dashboards and Web Applications | `--dashboards`    | `--security`                |                                                                                                                                                                                                                                                                                                                                                                                                  |
| System States                   | `--systemstates`  | `--security`                | - Feeds may require additional updates if servers used for migration have different domain names<br>- Cannot be migrated between 2020R1 and 2020R2 servers                                                                                                                                                                                                                                       |
| Tag Ingestion and Tag History   | `--tags`          | `--security`                |                                                                                                                                                                                                                                                                                                                                                                                                  |
| Tag Alarm Rules                 | `--tagrule`       | `--security`<br>`--notification` |                                                                                                                                                                                                                                                                                                                                                                                                  |
| Alarm Instances                 | `--alarms`        | `--security`<br>`--notification` | - Cannot be migrated between 2020R1 and 2020R2 servers                                                                                                                                                                                                                                                                                                                                           |
| Asset Alarm Rules               | `--assetrule`     | `--security`<br>`--notification` |                                                                                                                                                                                                                                                                                                                                                                                                  |
| Asset Management                | `--assets`        | `--security`<br>`--files`<br>`--tags`        |                                                                                                                                                                                                                                                                                                                                                                                                  |
| Test Monitor                    | `--tests`         | `--security`<br>`--file`         |                                                                                                                                                                                                                                                                                                                                                                                                  |
| Systems                         | `--systems`       | `--security`<br>`--tags`<br>`--file`  | - _WARNING:_ Captured systems data contains encrypted secret information and should not be copied to a publicly accessible location.<br>- To capture/restore systems, a secret must be provided using the `--secret <SECRET>` command line flag. Captured systems data will require the same secret to be provided as was provided during capture in order to be able to decrypt sensitive data. |

There are plans to support the following services in the future:
- OPC UA Client: `--opc`
- TDM `--tdm`
- Cloud Connector `--cloud`
