import math
import time
from pathlib import Path

from rhinos_buddy import sensors as S
from rhinos_buddy.engine import Engine, load_config
from rhinos_buddy.metrics import human_rate

# Shape of LibreHardwareMonitor's data.json (Text/Children/Value, decimal comma, "-" = no reading)
LHM = {
    "Text": "Sensor", "Children": [{
        "Text": "EXAMPLE-PC", "Children": [
            {"Text": "Example CPU 8-Core", "Children": [
                {"Text": "Load", "Children": [
                    {"Text": "CPU Total", "Value": "7,5 %", "Children": []},
                    {"Text": "CPU Core #1", "Value": "3,0 %", "Children": []}]},
                {"Text": "Temperatures", "Children": [
                    {"Text": "Core (Tctl/Tdie)", "Value": "48,6 °C", "Children": []},
                    {"Text": "CCD1 (Tdie)", "Value": "41,0 °C", "Children": []}]}]},
            {"Text": "Example Integrated Graphics", "Children": [  # integrated GPU, tiny memory
                {"Text": "Load", "Children": [{"Text": "GPU Core", "Value": "1,0 %", "Children": []}]},
                {"Text": "Temperatures", "Children": [{"Text": "GPU Core", "Value": "40,0 °C", "Children": []}]},
                {"Text": "Data", "Children": [{"Text": "GPU Memory Total", "Value": "512,0 MB", "Children": []}]}]},
            {"Text": "Example Discrete Graphics", "Children": [
                {"Text": "Load", "Children": [{"Text": "GPU Core", "Value": "23,0 %", "Children": []}]},
                {"Text": "Temperatures", "Children": [
                    {"Text": "GPU Core", "Value": "55,5 °C", "Children": []},
                    {"Text": "GPU Hot Spot", "Value": "-", "Children": []}]},
                {"Text": "Data", "Children": [
                    {"Text": "GPU Memory Used", "Value": "2048,0 MB", "Children": []},
                    {"Text": "GPU Memory Total", "Value": "8192,0 MB", "Children": []}]}]},
        ]}]}


def test_parse_number_locales():
    assert S.parse_number("45,5 °C") == 45.5
    assert S.parse_number("12.3 %") == 12.3
    assert math.isnan(S.parse_number("-"))
    assert math.isnan(S.parse_number(""))


def test_parse_lhm_picks_cpu_and_discrete_gpu():
    r = S.parse_lhm(LHM)
    assert r["cpu"] == 7.5 and r["cpu_temp"] == 48.6
    assert r["gpu"] == 23.0 and r["gpu_temp"] == 55.5  # the discrete GPU, not the iGPU
    assert r["gpu_mem_used_gb"] == 2.0 and r["gpu_mem_total_gb"] == 8.0 and r["gpu_mem"] == 25.0


def test_parse_nvidia_smi():
    r = S.parse_nvidia_smi("31, 47, 1024, 8192\n")
    assert r["gpu"] == 31 and r["gpu_temp"] == 47
    assert r["gpu_mem_used_gb"] == 1.0 and r["gpu_mem"] == 12.5
    assert S.parse_nvidia_smi("") == {}
    assert S.parse_nvidia_smi("[N/A], [N/A], [N/A], [N/A]") == {}


def test_human_rate():
    assert human_rate(350) == "350 KB/s"
    assert human_rate(1536) == "1.5 MB/s"


def _engine(tmp_path, widgets):
    p = tmp_path / "c.toml"
    p.write_text('[display]\ndecimal = ","\n[sensors]\nlhm = false\nnvidia_smi = false\n' + widgets)
    cfg = load_config(p)
    cfg["device"] = {"type": "simulator", "output": str(tmp_path / "o.png")}
    return Engine(cfg)


def test_text_in_portuguese_with_comma_and_missing_sensor(tmp_path):
    eng = _engine(tmp_path, '''
[[widget]]
type = "text"
x = 0
y = 0
w = 400
h = 30
text = "{dia_semana}, {now:%d} de {mes} de {now:%Y} | RAM {ram_used_gb:.1f} GB | GPU {gpu_temp:.0f} °C | {net_down_h}"
''')
    m = eng.ctx.metrics
    m.get()
    m._data = dict(m._data, ram_used_gb=11.4, net_down_h="1.2 MB/s")
    m._t = time.monotonic() + 100
    w = eng.pages[0].widgets[0]
    txt = w.current_text()
    assert "11,4 GB" in txt and "1,2 MB/s" in txt        # decimal comma
    assert "GPU -- °C" in txt                            # nan -> "--"
    import datetime
    d = datetime.datetime.now()
    assert f"de {['janeiro','fevereiro','março','abril','maio','junho','julho','agosto','setembro','outubro','novembro','dezembro'][d.month-1]} de {d.year}" in txt


def test_bar_with_missing_sensor_does_not_crash(tmp_path):
    eng = _engine(tmp_path, '[[widget]]\ntype="bar"\nx=0\ny=0\nw=100\nh=10\nmetric="gpu"\n')
    eng.display.open()
    eng.step(time.monotonic())  # gpu is nan -> must render as empty bar
    assert eng.pages[0].widgets[0].error is None
