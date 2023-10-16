
Edit wsjtx_influxdb/config.py

```
pip install -r requirements.txt
python -m wsjtx_influxdb
```

---

Copy wsjtx logs from `~/.local/share/WSJT-X/ALL.TXT`
Run `python -m wsjtx_influxdb --reprocess`.
This deletes the existing database, and imports all spots from wsjtx's logfile.
