from pathlib import Path

from specer.utils import generate_config_from_template


def test_generate_config_rewrites_cpu2017_1_0_gcc_template(tmp_path, monkeypatch):
    spec_root = tmp_path / "spec2017"
    config_dir = spec_root / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "Example-gcc-linux-x86.cfg").write_text(
        "\n".join(
            [
                "%define label mytest                # (2)      Use a label meaningful to *you*.",
                "#%define GCCge10  # EDIT: remove the '#' from column 1 if using GCC 10 or later",
                "tune                 = base,peak  # EDIT if needed: set to \"base\" for old GCC.",
                "intrate,fprate:",
                "   copies           = 1   # EDIT to change number of copies (see above)",
                "%ifndef %{gcc_dir}",
                "%   define  gcc_dir        /opt/rh/devtoolset-7/root/usr  # EDIT (see above)",
                "%endif",
            ]
        )
    )

    monkeypatch.setattr("specer.utils.detect_gcc_version", lambda: 13)
    monkeypatch.setattr("specer.utils.detect_gcc_path", lambda: "/usr")

    config_path = generate_config_from_template(
        cores=2,
        spec_root=spec_root,
        tune="base",
        compiler="gcc",
    )

    assert config_path is not None
    content = Path(config_path).read_text()

    assert 'define label "specer"' in content
    assert "#%define GCCge10" not in content
    assert "%define GCCge10" in content
    assert 'define  gcc_dir        "/usr"' in content
    assert "/opt/rh/devtoolset-7/root/usr" not in content
    assert "copies           = 2" in content
