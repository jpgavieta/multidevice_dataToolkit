# MultiDevice DataToolkit

A python-based portable and customizable data processing pipeline for variable standardization and validation of multiple devices.
Includes a notebook to demonstrate how to use and apply the data for statistical analysis. 

The **etl (extract transform load) data pipeline** standardizes data variables, validates data types, and categorizes variables into usable dataframes (e.g. builds a GIS dataframe for mapping) — ready for data anlaysis and visualization between devices. 

The etl logic based on `device_types` as separate streams of data, not based on participants. 

It is expandable for more device types, which each require its own custom  parser. 

## Data Flow from Multiple Devices

The data pipeline starts from whereever the data is kept (either shared folder per device type, the cloud API of each device, or a database table of the device type). It is triggered upon command via `load.py` that tells `extract.py` to pull data from wherever, `transform.py` applies the parser logic specific to device, and returns an organized and subdivided dataframe per device.  

[![Flow of Data from Multiple Devices](multidevice_dataflow.png)](multidevice_dataflow.png)
---

## Structure of this Repository

```
multidevice_dataToolkit/
├── pyproject.toml
├── .env                          # gitignored — actual secret client credentials + DB connection vars, Metabase admin creds
├── .env.example                  # committed — variable names only
├── .gitignore
├── README.md
├── requirements.txt
├── crontab.txt                   # documented cron schedule, for reference
│
├── deploy/
│   ├── docker-compose.yml         # Postgres+PostGIS, Metabase, defined as services
│   ├── postgres/
│   │   └── init/
│   │       └── 01_enable_postgis.sql   # runs once on first container start
│   └── metabase/
│       └── metabase-data/          # Metabase's own app DB (bind-mounted volume, 
│
├── config/
│   └── devices.yaml               # device registry + site→credential mapping
│
├── src/
│   ├── main.py                    # entry point: loop over devices.yaml, run E→T→L
│   │
│   ├── general/
│   │   ├── __init__.py
│   │   ├── utils.py                # shared logic (e.g. column type autodetection), includes pipeline_runs health queries
│   │   ├── device_registry.py      # loads/validates devices.yaml
│   │   └── run_logger.py           # writes to pipeline_runs table
│   │
│   ├── extract/
│   │   ├── __init__.py
│   │   ├── extract.py              # threaded per-device pulls, rate-limit aware
│   │   ├── clients/
│   │   │   ├── __init__.py
│   │   │   ├── atmotube_client.py
│   │   │   └── fitbit_client.py
│   │   ├── config/
│   │   │   ├── __init__.py
│   │   │   ├── tokens.py           # resolves site → env var name → secret
│   │   │   └── secrets/            # gitignored — everything under here, no exceptions
│   │   │       ├── fitbit/
│   │   │       │   ├── client_secret.json # shared OAuth client, one file
│   │   │       │   ├── accounts.yml       # device_id: google_account 
│   │   │       │   └── tokens/      
│   │   │       │       ├── fitbit_ko1_01.json
│   │   │       │       ├── fitbit_ko1_02.json
│   │   │       │       └── ...
│   │   │       └── atmotube/
│   │   │           └── ...
│   │   └── utils.py
│   │
│   ├── transform/
│   │   ├── __init__.py
│   │   ├── transform.py            # per-device parsing, UTC conversion
│   │   ├── parsers/
│   │   │   ├── __init__.py
│   │   │   ├── atmotube.py
│   │   │   └── fitbit.py
│   │   └── utils.py
│   │
│   └── load/
│       ├── __init__.py
│       ├── load.py                 # single serialized write step, upserts
│       ├── schema.sql              # devices, participants, device_assignments, pipeline_runs, readings tables # DB —  now includes PostGIS-specific DDL
│        └── migrations/            # DB — schema change history, see below
│            ├── 0001_init_schema.sql
│            └── 0002_add_participant_view.sql
│                
│
├── docs/                           # GitHub Pages — manual notebooks + html rendering helpers in utils
│   ├── atmotube
│   │   ├── datasheet.md
│   │   └── report.ipynb
│   ├── __init__.py
│   ├── manual.ipynb
│   ├── stats.py
│   └── utils.py                    
│
└── notifications/
    └── notify.py                    # email/Slack alert on pipeline_runs failure
```

 
