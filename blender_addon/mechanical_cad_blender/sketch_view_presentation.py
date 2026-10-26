"""Reversible mesh visibility for one explicitly owned native sketch viewport.

This presentation filter controls mesh context in that SpaceView3D only. It
never changes objects, collections, scenes, or any other viewport. The session
owns this resource and must restore it on every exit; there are no handlers,
timers, fallback viewport searches, or process-bound references here.
"""


class MeshVisibilityLease:
    """Temporarily set one VIEW_3D space's mesh-visibility filter.

    Acquisition errors raise RuntimeError after attempting a conditional rollback.
    ``restore()`` returns an empty string on success, or a cleanup diagnostic. It
    drops its native reference even when the captured space no longer exists.
    An external change away from the owned value is preserved. Ownership is
    value-based: writing the same value cannot be distinguished from no change.
    """

    __slots__ = ("_space", "_original", "_owned")

    def __init__(self, space, *, visible=False):
        if type(visible) is not bool:
            raise TypeError("Visibility must be boolean.")
        self._owned = visible
        self._space = None
        self._original = None
        message = ""
        try:
            if space.type != "VIEW_3D":
                raise ValueError("Mesh visibility requires the owned VIEW_3D space.")
            original = space.show_object_viewport_mesh
            if type(original) is not bool:
                raise TypeError("The native mesh-visibility filter must be a boolean.")
            # Capture before writing so even a partially failed setter can be
            # rolled back, without looking up a replacement area or space.
            self._space = space
            self._original = original
            space.show_object_viewport_mesh = visible
            if space.show_object_viewport_mesh is not visible:
                raise RuntimeError("The owned viewport did not accept mesh visibility.")
        except Exception as exc:
            message = f"Could not set sketch mesh visibility: {type(exc).__name__}: {exc}"
            cleanup_error = self.restore()
            if cleanup_error:
                message += f" Cleanup also failed: {cleanup_error}"
            # Do not leave an extra local native reference in this traceback.
            space = None
        # Raise outside the exception handler so even __context__ cannot retain
        # a native getter/setter traceback after failed acquisition.
        if message:
            raise RuntimeError(message)

    def restore(self):
        """Release once, restoring only the captured space's still-owned value.

        Detach first: repeated or reentrant cleanup never accesses old RNA, even
        after a destroyed-space error. A changed area or current viewport does
        not redirect restoration to a new space.
        """
        space, self._space = self._space, None
        original, self._original = self._original, None
        if space is None:
            return ""
        try:
            if space.show_object_viewport_mesh is self._owned and original is not self._owned:
                space.show_object_viewport_mesh = original
        except Exception as exc:
            return f"Could not restore sketch mesh visibility: {type(exc).__name__}: {exc}"
        finally:
            space = None
        return ""


class SketchContextLease(MeshVisibilityLease):
    """Keep reference meshes visible without exposing tessellation diagonals.

    A CAD solid is a triangulated display cache, not a boundary-edge mesh.
    Blender's wireframe shading (the original sketch workspace default) draws
    those artificial diagonals. Temporarily use solid shading in that case and
    disable the viewport wire overlay, without touching any object or geometry.
    Depth/curvature cavity cues keep blind-pocket rims visible when their floor
    and top face have identical lighting in a normal orthographic view.
    User changes away from each owned value survive cleanup independently.
    """

    __slots__ = ("_presentation",)

    def __init__(self, space):
        self._presentation = []
        super().__init__(space, visible=True)
        message = ""
        try:
            if space.shading.type == "WIREFRAME":
                self._set(space.shading, "type", "SOLID")
            self._set(space.overlay, "show_wireframes", False)
            self._set(space.shading, "show_cavity", True)
            self._set(space.shading, "cavity_type", "BOTH")
            # Screen curvature marks the rim, while world cavity adds depth.
            # These are native shading cues, never topology/selection evidence.
            self._set(space.shading, "curvature_ridge_factor", 2.0)
            self._set(space.shading, "curvature_valley_factor", 2.0)
            self._set(space.shading, "cavity_ridge_factor", 3.0)
            self._set(space.shading, "cavity_valley_factor", 3.0)
        except Exception as exc:
            message = f"Could not prepare sketch context: {type(exc).__name__}: {exc}"
            cleanup_error = self.restore()
            if cleanup_error:
                message += f" Cleanup also failed: {cleanup_error}"
            space = None
        if message:
            raise RuntimeError(message)

    def _set(self, target, attribute, value):
        original = getattr(target, attribute)
        self._presentation.append((target, attribute, original, value))
        setattr(target, attribute, value)
        if getattr(target, attribute) != value:
            raise RuntimeError(f"The owned viewport did not accept {attribute}.")

    def restore(self):
        settings, self._presentation = self._presentation, []
        diagnostics = []
        for target, attribute, original, owned in reversed(settings):
            try:
                if getattr(target, attribute) == owned and original != owned:
                    setattr(target, attribute, original)
            except Exception as exc:
                diagnostics.append(
                    f"Could not restore sketch {attribute}: {type(exc).__name__}: {exc}"
                )
        visibility_error = super().restore()
        if visibility_error:
            diagnostics.append(visibility_error)
        return " ".join(diagnostics)
