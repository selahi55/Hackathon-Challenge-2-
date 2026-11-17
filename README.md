# Hollandse Luchten Challenge 2: PM2.5 hotspot screening

How to run our solution on your own computer, from scratch. It works on Windows, macOS and Linux. You need Python 3.11
or newer (the tool below installs it if it is missing), about 2 GB of free disk space, and an internet connection (for
the packages, the data download, and the map tiles in the app). Nothing is uploaded anywhere.

## 1. Get the code

```bash
git clone https://github.com/selahi55/Hackathon-Challenge-2-.git
cd Hackathon-Challenge-2-
```

## 2. Install uv

[uv](https://docs.astral.sh/uv/getting-started/installation/) sets up the Python environment.

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Open a new terminal afterwards so that `uv` is found.

## 3. Download the sensor data

The sensor files (84 MB) are too large for git. Download them from [Zenodo](https://zenodo.org/records/23762846) into
the `data/` folder. The weather, reference-station and resident files are already in the repository.

```bash
# Windows (PowerShell): use curl.exe, because "curl" is an alias there
curl.exe -L -o data/data_sensors.parquet "https://zenodo.org/records/23762846/files/data_sensors.parquet?download=1"
curl.exe -L -o data/metadata_sensors.parquet "https://zenodo.org/records/23762846/files/metadata_sensors.parquet?download=1"

# macOS / Linux
curl -L -o data/data_sensors.parquet "https://zenodo.org/records/23762846/files/data_sensors.parquet?download=1"
curl -L -o data/metadata_sensors.parquet "https://zenodo.org/records/23762846/files/metadata_sensors.parquet?download=1"
```

## 4. Install the packages

```bash
uv sync
```

This creates a `.venv/` folder with the exact package versions from `uv.lock`. It takes a few minutes the first time.

## 5. Start the app from the notebook

```bash
uv run jupyter lab notebooks/04_hotspot_screening_app.ipynb
```

(In VS Code: open the notebook and choose the `.venv` kernel.)

**Run the first cell only.** It writes the app to `output/pm25_hotspot_app.py`, starts it on your computer, and opens
it in your browser at <http://127.0.0.1:8501>. If that port is busy, the cell picks another one and prints the address.
Do not run the second cell: it installs packages with pip, which is not needed because step 4 already did that.

## 6. Run an analysis

The file paths in the app's sidebar are already correct. Press **Run analysis**.

- With the default settings it analyses the first 14 days in the data (January 2020). This takes 10 to 20 seconds.
- For recent data, first fill in *Start timestamp* `2025-03-01` and *End timestamp, exclusive* `2025-03-15`, then press
  **Run analysis**.

You should then see "Analysis complete", four numbers (sensors, assessable sensor-hours, flagged sensor-hours, recurring
candidates) and five tabs: *Regional map*, *Episodes*, *Sensor explorer*, *Wind direction* and *Method & diagnostics*.
As a check, the March 2025 window gives 150 sensors, 45,084 assessable sensor-hours, 895 flagged sensor-hours and
2 recurring candidates; the default window gives 119, 32,731, 1,742 and 8.

To stop the app, run `streamlit_process.terminate()` in a notebook cell, or close the Jupyter session.

## If something goes wrong

| Problem | Fix |
|---|---|
| "Missing packages in THIS notebook's Python environment" | The notebook is not using the `.venv` kernel. Start it with `uv run jupyter lab ...` as in step 5, or pick the `.venv` kernel. |
| "Could not find data/data_sensors.parquet" | Do step 3, and open the notebook from inside the repository folder. |
| Memory error during *Run analysis* | Use a shorter window (only the selected window is kept in memory) and close other programs. |
| The map has no background | The map tiles need internet. The analysis itself works without them. |
| `uv` is not found after installing | Open a new terminal. |

## Optional: the sensor viewer (Windows only)

`PMsensorViewNoiseSuppression/PMsensorViewer.exe` is a separate desktop viewer for the sensor locations. It needs its
data file `PMdata/data_sensors.xlsx` (444 MB, too large for GitHub):

1. Download it from **[team to insert link before submission]** and save it as
   `PMsensorViewNoiseSuppression/PMdata/data_sensors.xlsx`.
2. Start `PMsensorViewer.exe`. It is not code-signed, so Windows may show a warning. Its SHA-256 is
   `955A72B4524C098420C7305114F442FA251ADD7E73A61F04C8C582061BFBAFD4`; you can check it with
   `Get-FileHash PMsensorViewNoiseSuppression/PMsensorViewer.exe` in PowerShell.

The app above does not need the viewer.
