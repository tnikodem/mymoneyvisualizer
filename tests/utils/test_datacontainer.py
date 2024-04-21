import os
from mymoneyvisualizer.utils.datacontainer import OrderedDataContainer


def test_create_accounts(tmp_path):
    container_filepath = str(tmp_path)+"/blub/test_datacontainer.yaml"

    class TestObject:
        def __init__(self, i):
            self.name = i

        def to_dict(self):
            return {"name": str(self.name), "obj": "blub"}

    # new container
    odc = OrderedDataContainer(container_filepath=container_filepath)
    assert odc is not None
    assert len(odc) == 0

    # add objects
    for i in range(3):
        o = odc.add(name=i, obj=TestObject(i))
        assert len(odc) == i+1

    # save container
    odc.save()
    assert os.path.isfile(container_filepath)

    # delete obj
    odc.delete(0)
    assert len(odc) == 2

    # check in method
    assert 2 in odc

    # check print
    odc.__repr__()

    # load container from saved file
    odc2 = OrderedDataContainer(container_filepath=container_filepath)
    assert len(odc) == len(odc2)
