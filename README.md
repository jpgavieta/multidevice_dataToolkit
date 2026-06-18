# MultiDevice DataToolkit

A python-based portable and customizable data processing pipeline to notebook-based html viewer (using juypter-viewer) for the statistical summaries and validations of multiple devices.

The **etl (extract transform load) data pipeline** standardizes data variables, validates data types, and categorizes variables into usable dataframes (e.g. builds a GIS dataframe for mapping) — ready for data anlaysis between devices. 

The etl logic based on `device_types` as separate streams of data, not based on participants. 
It is expandable for more device types, which each require its own specific parser. 

<a href="multidevice_dataflow.png">
  <img src="multidevice_dataflow.png" alt="Flow of Data" width="600" />
</a>  

---

## What's in here?

```
/
├── .vscode/tasks.json      ## Protoype mode: mounts onto shared file cloud, does not keep any local copies
|                             
├── src/   
|   ├── __init__.py   
|   ├── utils.py                # Global functions (column type autodetection logic based on entire df not per row)
|   |            
|   └── etl/                ## Extract, Transform, Load Logic --------------------------------------------------
│       ├── __init__.py        
|       ├── extract.py          # Reads raw data (current method: reads files; later upgrade: fetch apis)
|       ├── transform.py        # Applies parser (device-agnostic and extract-agnostic)
|       └── parsers/                # Builds dfs (device-specific)
|           ├── __init__.py      
|           ├── atmotube.py      
|           ├── ponyopi.py       
|           └── fitbit.py            
|      
├── notebooks/              ## Vizualizes data as html report
|   └── main.ipynb 
| 
├── environment.yml             
|                     
└── docs/                       # Documentation per device
    ├── Atmotube_datasheet.md
    └── etc.
```

 
