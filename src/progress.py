from typing import Any, Iterable, Optional, Sequence, Sized, Union, overload

from dotenv import load_dotenv
from rich.progress import BarColumn, Progress, ProgressType, SpinnerColumn, TaskID, TextColumn, TimeElapsedColumn

load_dotenv()


class ModifiedProgress(Progress):
    """Modified Progress class for simpler usage"""

    def increment(self, steps: float = 1, description: str | None = None) -> None:
        """Simple increment update"""
        self.update(self.task_ids[0], description=description, advance=steps)

    @overload
    def update(self, description: str) -> None:
        """Simple description update"""
        ...

    @overload
    def update(self, completed: float, total: float) -> None:
        """Simple completed/total update"""
        ...

    @overload
    def update(self, description: str, completed: float, total: float) -> None:
        """Simple completed/total update with description"""
        ...

    @overload
    def update(
        self,
        task_id: TaskID,
        *,
        total: Optional[float] = None,
        completed: Optional[float] = None,
        advance: Optional[float] = None,
        description: Optional[str] = None,
        visible: Optional[bool] = None,
        refresh: bool = False,
        **fields: Any,
    ) -> None: ...
    def update(self, *args, **kwargs) -> None:
        task_id = self.task_ids[0]

        # Check for description pattern: update(description: str) or update(description="str")
        if (len(args) == 1 and isinstance(args[0], str)) or (
            len(args) == 0 and len(kwargs) == 1 and "description" in kwargs and isinstance(kwargs["description"], str)
        ):
            if len(args) == 1:
                super().update(task_id=task_id, description=args[0], **kwargs)
            else:
                super().update(task_id=task_id, **kwargs)

        # Check for completed/total pattern: update(completed, total) or update(completed=x, total=y)
        elif (len(args) == 2 and all(isinstance(arg, (int, float)) for arg in args)) or (
            len(args) == 0
            and len(kwargs) == 2
            and "completed" in kwargs
            and "total" in kwargs
            and all(isinstance(kwargs[k], (int, float)) for k in ["completed", "total"])
        ):
            if len(args) == 2:
                super().update(task_id=task_id, completed=float(args[0]), total=float(args[1]), **kwargs)
            else:
                super().update(task_id=task_id, **kwargs)

        # Check for description + completed/total pattern: update(description, completed, total) or mixed kwargs
        elif (len(args) == 3 and isinstance(args[0], str) and all(isinstance(arg, (int, float)) for arg in args[1:])) or (
            len(args) == 0
            and len(kwargs) == 3
            and "description" in kwargs
            and "completed" in kwargs
            and "total" in kwargs
            and isinstance(kwargs["description"], str)
            and all(isinstance(kwargs[k], (int, float)) for k in ["completed", "total"])
        ):
            if len(args) == 3:
                super().update(task_id=task_id, description=args[0], completed=float(args[1]), total=float(args[2]), **kwargs)
            else:
                super().update(task_id=task_id, **kwargs)

        # Fallback: pass everything as kwargs
        else:
            super().update(task_id=task_id, **kwargs)


def progress_spinner(message: str = "", transient: bool = True) -> ModifiedProgress:
    """Creates a progress spinner for a single task"""

    progress = ModifiedProgress(
        SpinnerColumn(),
        TimeElapsedColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=transient,
    )
    progress.add_task(message)
    return progress


def progress_bar(message: str = "", total: float = 100, transient: bool = True) -> ModifiedProgress:
    """Creates a progress bar for a single task"""

    progress = ModifiedProgress(
        SpinnerColumn(),
        TimeElapsedColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        transient=transient,
    )
    progress.add_task(message, completed=0, total=total)
    return progress


def progress_track(
    sequence: Union[Sequence[ProgressType], Iterable[ProgressType]], message: str = "", transient: bool = True
) -> Iterable[ProgressType]:
    """Creates a progress bar for a single simple task"""
    total = len(sequence) if isinstance(sequence, Sized) else 0
    with progress_bar(message, total=total, transient=transient) as progress:
        for item in sequence:
            yield item
            progress.increment()
