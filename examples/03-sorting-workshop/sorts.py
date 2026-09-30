"""Sorting algorithms, their traces and a comparison plot."""
import random

from lattice import ArrayTrace


def bubble_sort(a):
    n = len(a)
    for end in range(n - 1, 0, -1):
        swapped = False
        for i in range(end):
            if a[i] > a[i + 1]:
                a[i], a[i + 1] = a[i + 1], a[i]
                swapped = True
        if not swapped:
            return a
    return a


def insertion_sort(a):
    for j in range(1, len(a)):
        key = a[j]
        i = j - 1
        while i >= 0 and a[i] > key:
            a[i + 1] = a[i]
            i -= 1
        a[i + 1] = key
    return a


def bubble_trace(values):
    a = list(values)
    t = ArrayTrace(a)
    t.frame(caption="Unsorted input", meta={"line": 1})
    n = len(a)
    sorted_cells = {}
    for end in range(n - 1, 0, -1):
        swapped = False
        for i in range(end):
            t.frame(marks={i: "compare", i + 1: "compare"}, pointers={"i": i},
                    caption=f"Compare {a[i]} and {a[i + 1]}", meta={"line": 6})
            if a[i] > a[i + 1]:
                a[i], a[i + 1] = a[i + 1], a[i]
                swapped = True
                t.frame(values=a, marks={i: "swap", i + 1: "swap"}, pointers={"i": i},
                        caption="Out of order: swap", meta={"line": 7})
        sorted_cells[end] = "sorted"
        t.frame(cells=dict(sorted_cells), pointers={"i": None},
                caption=f"{a[end]} has bubbled to its final place", meta={"line": 9})
        if not swapped:
            t.frame(cells={k: "sorted" for k in range(n)}, caption="No swap in a full pass: done early",
                    meta={"line": 10})
            return t
    t.frame(cells={k: "sorted" for k in range(n)}, caption="Sorted", meta={"line": 11})
    return t


def insertion_trace(values):
    a = list(values)
    t = ArrayTrace(a)
    t.frame(cells={0: "sorted"}, caption="A single element is a sorted prefix", meta={"line": 1})
    for j in range(1, len(a)):
        key = a[j]
        t.frame(marks={j: "pivot"}, pointers={"j": j}, panel={"key": key},
                caption=f"Insert {key} into the sorted prefix", meta={"line": 3})
        i = j - 1
        while i >= 0 and a[i] > key:
            t.frame(marks={i: "compare", i + 1: "pivot"}, pointers={"i": i, "j": j},
                    caption=f"{a[i]} > {key}: shift it right", meta={"line": 5})
            a[i + 1] = a[i]
            a[i] = key
            t.frame(values=a, marks={i: "pivot", i + 1: "swap"}, pointers={"i": i, "j": j}, meta={"line": 6})
            i -= 1
        t.frame(cells={k: "sorted" for k in range(j + 1)}, pointers={"i": None, "j": None},
                caption=f"Prefix of length {j + 1} is sorted", meta={"line": 8})
    return t


def quick_trace(values):
    a = list(values)
    t = ArrayTrace(a)
    t.frame(caption="Unsorted input")
    done = {}

    def sort(lo, hi):
        if lo > hi:
            return
        if lo == hi:
            done[lo] = "sorted"
            t.frame(cells=dict(done), caption=f"{a[lo]} is alone: in place")
            return
        pivot = a[hi]
        t.frame(marks={hi: "pivot"}, pointers={"lo": lo, "hi": hi}, caption=f"Pivot {pivot} on a[{lo}..{hi}]")
        i = lo
        for j in range(lo, hi):
            t.frame(marks={hi: "pivot", j: "compare"}, pointers={"i": i, "j": j},
                    caption=f"Is {a[j]} < {pivot}?")
            if a[j] < pivot:
                a[i], a[j] = a[j], a[i]
                if i != j:
                    t.frame(values=a, marks={hi: "pivot", i: "swap", j: "swap"}, pointers={"i": i, "j": j},
                            caption="Yes: move it left of the boundary")
                i += 1
        a[i], a[hi] = a[hi], a[i]
        done[i] = "sorted"
        t.frame(values=a, cells=dict(done), pointers={"i": None, "j": None, "lo": None, "hi": None},
                caption=f"Pivot {pivot} lands at index {i}")
        sort(lo, i - 1)
        sort(i + 1, hi)

    sort(0, len(a) - 1)
    t.frame(cells={k: "sorted" for k in range(len(a))}, caption="Sorted")
    return t


def _count(sort_name, a):
    count = 0
    a = list(a)
    if sort_name == "bubble":
        for end in range(len(a) - 1, 0, -1):
            swapped = False
            for i in range(end):
                count += 1
                if a[i] > a[i + 1]:
                    a[i], a[i + 1] = a[i + 1], a[i]
                    swapped = True
            if not swapped:
                break
    elif sort_name == "insertion":
        for j in range(1, len(a)):
            key, i = a[j], j - 1
            while i >= 0:
                count += 1
                if a[i] <= key:
                    break
                a[i + 1] = a[i]
                i -= 1
            a[i + 1] = key
    else:
        stack = [(0, len(a) - 1)]
        while stack:
            lo, hi = stack.pop()
            if lo >= hi:
                continue
            pivot, i = a[hi], lo
            for j in range(lo, hi):
                count += 1
                if a[j] < pivot:
                    a[i], a[j] = a[j], a[i]
                    i += 1
            a[i], a[hi] = a[hi], a[i]
            stack += [(lo, i - 1), (i + 1, hi)]
    return count


def comparison_plot(ax):
    rng = random.Random(7)
    sizes = [10, 50, 100, 200, 400, 800]
    for name in ["bubble", "insertion", "quick"]:
        counts = []
        for n in sizes:
            runs = [_count(name, [rng.random() for _ in range(n)]) for _ in range(5)]
            counts.append(sum(runs) / len(runs))
        ax.plot(sizes, counts, marker="o", label=name)
    ax.set_xlabel("input size n")
    ax.set_ylabel("comparisons (mean of 5 runs)")
    ax.set_yscale("log")
    ax.legend()
