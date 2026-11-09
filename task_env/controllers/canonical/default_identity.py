"""Subject-owned default for declared canonical joint-effort channels.

The unbound Controller cannot produce an action. Binding uses the existing
source-bound physical owner; provider admission and coupled-transmission checks
remain at the normal command submission boundary.
"""
class DefaultCanonicalController:
    """Bind once to the existing direct-effort Controller for this subject."""

    def __init__(self):
        self._controller = None
        self._children = ()

    @property
    def is_bound(self):
        return self._controller is not None or bool(self._children)

    def bind(self, subject, binding, *, writer_id, units, action_key='torque'):
        if self.is_bound:
            raise RuntimeError('default Controller is already bound')
        from ...runtime.sessions.physical_control import ControlledSubjectV1
        if type(subject) is not ControlledSubjectV1:
            raise TypeError('default Controller requires a declared controlled subject')
        # The existing owner checks source, writer, unit and ordered channels.
        # It does not promise that the provider admits a coupled transmission.
        controller = subject.default_effort_controller(
            binding, writer_id=writer_id, units=units, action_key=action_key)
        self._controller = controller
        return self

    def bind_many(self, binding, declarations):
        """Bind nested subjects as separate writers for the existing compositor.

        Each declaration is (subject, writer_id, units).  Construct everything
        before publishing children, so a bad declaration cannot partially bind
        this owner.  PhysicalControlExecutionV1 remains the only compositor.
        """
        if self.is_bound:
            raise RuntimeError('default Controller is already bound')
        if type(declarations) is not tuple or not declarations:
            raise ValueError('nested default requires immutable subject declarations')
        children = []
        writers, subjects = set(), set()
        for row in declarations:
            if type(row) is not tuple or len(row) != 3:
                raise ValueError('nested default declaration requires subject, writer and units')
            subject, writer, units = row
            if writer in writers or getattr(subject, 'subject_id', None) in subjects:
                raise ValueError('nested default requires unique subjects and writers')
            child = type(self)().bind(subject, binding, writer_id=writer, units=units)
            writers.add(writer)
            subjects.add(subject.subject_id)
            children.append(child)
        self._children = tuple(children)
        return self._children

    @property
    def controllers(self):
        if self._children:
            return self._children
        if self._controller is not None:
            return (self,)
        raise RuntimeError('default Controller requires a source-bound subject')

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        controller = self._controller
        if controller is None:
            if self._children:
                raise RuntimeError('nested defaults must use the existing multi-controller compositor')
            raise RuntimeError('default Controller requires a source-bound subject')
        return getattr(controller, name)
