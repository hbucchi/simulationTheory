class Module:
    """Base class for agent modules. Override ``on_step``."""

    def on_step(self, agent, world):
        raise NotImplementedError

    def to_dict(self):
        """Settings worth showing in the UI."""
        return {}
