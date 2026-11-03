
def test_gateway_network_active(gateway_network_active):
    assert gateway_network_active


def test_gateway_ping(gateway_reachable_on_network):
    assert gateway_reachable_on_network
