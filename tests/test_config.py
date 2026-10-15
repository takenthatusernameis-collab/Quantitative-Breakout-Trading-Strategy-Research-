"""Test configuration."""
import unittest
from breakout_research import config


class TestConfig(unittest.TestCase):
    def test_load_manifests(self):
        spec = config.load_research_spec()
        self.assertEqual(spec['protocol_version'], 'v1')
        self.assertEqual(spec['specification_hash'],
                         '2d22e70246cf023218ef6dd0cb655897836b310e1a6e6969d934f52d06e79085')

    def test_get_configurations(self):
        cfg_manifest = config.load_config_manifest()
        cfgs = config.get_configurations(cfg_manifest)
        self.assertEqual(len(cfgs), 2304)
