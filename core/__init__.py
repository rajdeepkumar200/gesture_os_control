"""Core CV, gesture and OS-control package.

Submodules are intentionally NOT pre-imported at package level so unit
tests / tooling can load only the lightweight pieces (e.g.
``gesture_classifier``) without pulling in heavy optional dependencies
such as ``cv2`` or ``mediapipe``.

Import sub-modules explicitly, e.g.::

    from core.gesture_classifier import GestureClassifier
    from core.action_dispatcher import ActionDispatcher
"""
