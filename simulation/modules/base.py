class Module:
    """Base class for agent modules. Override ``on_step``."""

    def on_step(self, agent, world):
        raise NotImplementedError
