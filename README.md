# Prescription dashboard for LINKR

This repository presents a schema for a plugin for LINKR.
It is based on the sample data from MIMIC-IV available in [physionet](https://physionet.org/files/mimic-iv-demo-omop/0.9/1_omop_data_csv/).

You can create a virtual environment using the command:

```sh
# Create the virtual env in the project repository
poetry install
# Activate the virtual env
poetry shell
```

To download the sample data:

```sh
python src/download.py
```

The sample date is download in the `data` folder.

## Dashboard using DASH

There is a schema of dashboard that could use as a template to create a LINKR plugin.
To run the dashboard in a local environment you can run the command:

```sh
python src/app_dashboard.py
```
