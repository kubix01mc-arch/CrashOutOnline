"""Interactive graph for finding the shortest round trip through plotted points."""

from __future__ import annotations

import heapq
import math
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

MAX_POINTS = 16
COORDINATE_LIMIT = 100
GRID_STEP = 20

Point = tuple[float, float]
Square = tuple[float, float, float, float]
Circle = tuple[float, float, float, bool]


def shortest_tour(
    points: list[Point],
    distances: list[list[float]] | None = None,
) -> tuple[list[int], float]:
    """Return the exact shortest closed tour, starting and ending at point zero."""
    if not points:
        raise ValueError("Add at least one point before calculating a route.")

    count = len(points)
    if distances is None:
        distances = [
            [
                math.hypot(
                    points[first][0] - points[second][0],
                    points[first][1] - points[second][1],
                )
                for second in range(count)
            ]
            for first in range(count)
        ]
    if len(distances) != count or any(len(row) != count for row in distances):
        raise ValueError("The distance matrix must have one row and column per point.")

    if count == 1:
        return [0, 0], 0.0

    # Held-Karp dynamic programming: each state records the cheapest path from
    # point zero through a subset of the other points to one endpoint.
    costs: dict[tuple[int, int], float] = {}
    parents: dict[tuple[int, int], int] = {}
    for endpoint in range(1, count):
        mask = 1 << (endpoint - 1)
        costs[(mask, endpoint)] = distances[0][endpoint]
        parents[(mask, endpoint)] = 0

    full_mask = (1 << (count - 1)) - 1
    for mask in range(1, full_mask + 1):
        for endpoint in range(1, count):
            endpoint_bit = 1 << (endpoint - 1)
            if not mask & endpoint_bit or mask == endpoint_bit:
                continue

            previous_mask = mask ^ endpoint_bit
            best_cost = math.inf
            best_previous = 0
            for previous in range(1, count):
                previous_bit = 1 << (previous - 1)
                if previous_mask & previous_bit:
                    candidate = costs[(previous_mask, previous)] + distances[previous][endpoint]
                    if candidate < best_cost:
                        best_cost = candidate
                        best_previous = previous

            costs[(mask, endpoint)] = best_cost
            parents[(mask, endpoint)] = best_previous

    last = min(
        range(1, count),
        key=lambda endpoint: costs[(full_mask, endpoint)] + distances[endpoint][0],
    )
    total_distance = costs[(full_mask, last)] + distances[last][0]
    if not math.isfinite(total_distance):
        raise ValueError("The points cannot all be connected without crossing a square.")

    reverse_path = [last]
    mask = full_mask
    while mask:
        endpoint = reverse_path[-1]
        previous = parents[(mask, endpoint)]
        mask ^= 1 << (endpoint - 1)
        if mask:
            reverse_path.append(previous)

    return [0, *reversed(reverse_path), 0], total_distance


def segment_crosses_square(start: Point, end: Point, square: Square) -> bool:
    """Return whether a segment enters a square's interior (its border is clear)."""
    x_min, y_min, x_max, y_max = square
    low, high = 0.0, 1.0
    for origin, delta, lower, upper in (
        (start[0], end[0] - start[0], x_min, x_max),
        (start[1], end[1] - start[1], y_min, y_max),
    ):
        if delta == 0:
            if not lower < origin < upper:
                return False
            continue
        first = (lower - origin) / delta
        second = (upper - origin) / delta
        low = max(low, min(first, second))
        high = min(high, max(first, second))
        if low >= high:
            return False
    return high > 0 and low < 1 and max(low, 0.0) < min(high, 1.0)


def segment_crosses_circle(start: Point, end: Point, circle: Circle) -> bool:
    """Return whether a segment enters the interior of a circle."""
    center_x, center_y, radius = circle[:3]
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return math.dist(start, (center_x, center_y)) < radius - 1e-8
    position = ((center_x - start[0]) * dx + (center_y - start[1]) * dy) / length_squared
    position = max(0.0, min(1.0, position))
    closest = start[0] + position * dx, start[1] + position * dy
    return math.dist(closest, (center_x, center_y)) < radius - 1e-8


def obstacle_aware_tour(
    points: list[Point],
    squares: list[Square],
    circles: list[Circle] | None = None,
) -> tuple[list[Point], float]:
    """Find the shortest closed tour with square obstacles and directed circle arcs."""
    circles = circles or []
    if any(
        x_min < x < x_max and y_min < y < y_max
        for x, y in points
        for x_min, y_min, x_max, y_max in squares
    ):
        raise ValueError("A point is inside a square. Move the point or clear that square.")
    if any(
        math.dist(point, (center_x, center_y)) < radius - 1e-8
        for point in points
        for center_x, center_y, radius in (circle[:3] for circle in circles)
    ):
        raise ValueError("A point is inside a circle. Move the point or clear that circle.")
    for center_x, center_y, radius in (circle[:3] for circle in circles):
        for x_min, y_min, x_max, y_max in squares:
            closest_x = max(x_min, min(center_x, x_max))
            closest_y = max(y_min, min(center_y, y_max))
            if math.hypot(center_x - closest_x, center_y - closest_y) < radius - 1e-8:
                raise ValueError("A circle cannot overlap a square obstacle.")
    for first in range(len(circles)):
        for second in range(first + 1, len(circles)):
            if math.dist(circles[first][:2], circles[second][:2]) < circles[first][2] + circles[second][2] - 1e-8:
                raise ValueError("Circles cannot overlap.")
    if len(points) == 1:
        return [points[0], points[0]], 0.0

    static_nodes = list(points)
    for square in squares:
        x_min, y_min, x_max, y_max = square
        static_nodes.extend(
            (x, y)
            for x, y in (
                (x_min, y_min),
                (x_min, y_max),
                (x_max, y_min),
                (x_max, y_max),
            )
            if not any(
                other[0] < x < other[2] and other[1] < y < other[3]
                for other in squares
            )
        )

    nodes = list(static_nodes)
    node_ids = {(round(x, 8), round(y, 8)): index for index, (x, y) in enumerate(nodes)}

    def add_node(point: Point) -> int:
        key = round(point[0], 8), round(point[1], 8)
        if key not in node_ids:
            node_ids[key] = len(nodes)
            nodes.append(point)
        return node_ids[key]

    circle_nodes: list[dict[float, int]] = []
    for circle_index, circle in enumerate(circles):
        center_x, center_y, radius = circle[:3]
        angles = {round(index * 2 * math.pi / 32, 10) for index in range(32)}
        for x, y in static_nodes:
            dx, dy = x - center_x, y - center_y
            distance = math.hypot(dx, dy)
            if distance <= radius:
                continue
            radial_angle = math.atan2(dy, dx)
            angles.add(round(radial_angle % (2 * math.pi), 10))
            tangent_offset = math.acos(radius / distance)
            angles.add(round((radial_angle + tangent_offset) % (2 * math.pi), 10))
            angles.add(round((radial_angle - tangent_offset) % (2 * math.pi), 10))
        for other_index, other_circle in enumerate(circles):
            if other_index != circle_index:
                angle_to_other = math.atan2(
                    other_circle[1] - center_y,
                    other_circle[0] - center_x,
                )
                angles.add(round(angle_to_other % (2 * math.pi), 10))

        angle_to_node: dict[float, int] = {}
        for angle in angles:
            boundary = center_x + radius * math.cos(angle), center_y + radius * math.sin(angle)
            angle_to_node[angle] = add_node(boundary)
        circle_nodes.append(angle_to_node)

    adjacency: list[list[tuple[int, float]]] = [[] for _ in nodes]
    for first in range(len(static_nodes)):
        for second in range(first + 1, len(static_nodes)):
            if any(segment_crosses_square(static_nodes[first], static_nodes[second], square) for square in squares):
                continue
            if any(segment_crosses_circle(static_nodes[first], static_nodes[second], circle) for circle in circles):
                continue
            distance = math.dist(static_nodes[first], static_nodes[second])
            adjacency[first].append((second, distance))
            adjacency[second].append((first, distance))

    for circle_index, (center_x, center_y, radius, clockwise) in enumerate(circles):
        angle_to_node = circle_nodes[circle_index]
        ordered_angles = sorted(angle_to_node)
        for index, angle in enumerate(ordered_angles):
            next_index = (index - 1) % len(ordered_angles) if clockwise else (index + 1) % len(ordered_angles)
            next_angle = ordered_angles[next_index]
            delta = (angle - next_angle) % (2 * math.pi) if clockwise else (next_angle - angle) % (2 * math.pi)
            start_node = angle_to_node[angle]
            end_node = angle_to_node[next_angle]
            adjacency[start_node].append((end_node, radius * delta))

            boundary_point = nodes[start_node]
            for target in range(len(static_nodes)):
                target_point = static_nodes[target]
                target_angle = math.atan2(target_point[1] - center_y, target_point[0] - center_x)
                if abs(math.atan2(math.sin(target_angle - angle), math.cos(target_angle - angle))) > 1e-7:
                    continue
                if any(
                    segment_crosses_square(boundary_point, target_point, square)
                    for square in squares
                ) or any(
                    other_index != circle_index
                    and segment_crosses_circle(boundary_point, target_point, other_circle)
                    for other_index, other_circle in enumerate(circles)
                ):
                    continue
                adjacency[start_node].append((target, math.dist(boundary_point, target_point)))

        for target, target_point in enumerate(static_nodes):
            dx, dy = target_point[0] - center_x, target_point[1] - center_y
            distance = math.hypot(dx, dy)
            if distance <= radius:
                continue
            for sign in (-1, 1):
                tangent_angle = round(
                    (math.atan2(dy, dx) + sign * math.acos(radius / distance)) % (2 * math.pi),
                    10,
                )
                boundary_point = nodes[angle_to_node[tangent_angle]]
                if any(
                    segment_crosses_square(target_point, boundary_point, square)
                    for square in squares
                ) or any(
                    other_index != circle_index
                    and segment_crosses_circle(target_point, boundary_point, other_circle)
                    for other_index, other_circle in enumerate(circles)
                ):
                    continue
                tangent_node = angle_to_node[tangent_angle]
                adjacency[target].append((tangent_node, math.dist(target_point, boundary_point)))

    for first in range(len(circles)):
        first_circle = circles[first]
        for second in range(first + 1, len(circles)):
            second_circle = circles[second]
            angle = math.atan2(
                second_circle[1] - first_circle[1],
                second_circle[0] - first_circle[0],
            )
            first_angle = round(angle % (2 * math.pi), 10)
            second_angle = round((angle + math.pi) % (2 * math.pi), 10)
            first_node = circle_nodes[first][first_angle]
            second_node = circle_nodes[second][second_angle]
            first_point, second_point = nodes[first_node], nodes[second_node]
            if any(
                segment_crosses_square(first_point, second_point, square)
                for square in squares
            ) or any(
                circle_index not in (first, second)
                and segment_crosses_circle(first_point, second_point, other_circle)
                for circle_index, other_circle in enumerate(circles)
            ):
                continue
            distance = math.dist(first_point, second_point)
            adjacency[first_node].append((second_node, distance))
            adjacency[second_node].append((first_node, distance))

    point_count = len(points)
    point_distances = [[math.inf] * point_count for _ in range(point_count)]
    predecessors: list[list[int | None]] = []
    for source in range(point_count):
        distances = [math.inf] * len(nodes)
        previous: list[int | None] = [None] * len(nodes)
        distances[source] = 0.0
        queue = [(0.0, source)]
        while queue:
            distance, current = heapq.heappop(queue)
            if distance > distances[current]:
                continue
            for neighbor, edge_distance in adjacency[current]:
                candidate = distance + edge_distance
                if candidate < distances[neighbor]:
                    distances[neighbor] = candidate
                    previous[neighbor] = current
                    heapq.heappush(queue, (candidate, neighbor))
        predecessors.append(previous)
        for target in range(point_count):
            point_distances[source][target] = distances[target]

    point_order, total_distance = shortest_tour(points, point_distances)
    route: list[Point] = []
    for source, target in zip(point_order, point_order[1:]):
        reverse_leg = [target]
        current = target
        while current != source:
            parent = predecessors[source][current]
            if parent is None:
                raise ValueError("The points cannot all be connected without crossing a square.")
            current = parent
            reverse_leg.append(current)
        leg = [nodes[index] for index in reversed(reverse_leg)]
        route.extend(leg if not route else leg[1:])
    return route, total_distance


class ShortestPathGraph:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.points: list[Point] = []
        self.point_names: list[str] = []
        self.squares: list[Square] = []
        self.circles: list[Circle] = []
        self.mode = "points"
        self.next_circle_clockwise = True
        self.drag_start: Point | None = None
        self.drag_square: Square | None = None
        self.drag_circle: Circle | None = None
        self.tour: list[Point] | None = None
        self.total_distance: float | None = None

        root.title("Shortest Round Trip")
        root.geometry("900x720")
        root.minsize(600, 500)

        controls = ttk.Frame(root, padding=(12, 10))
        controls.pack(fill=tk.X)

        ttk.Label(
            controls,
            text="Shortest Round Trip",
            font=("Segoe UI", 16, "bold"),
        ).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Label(controls, text="Next point name:").pack(side=tk.LEFT, padx=(0, 4))
        self.nickname = tk.StringVar()
        ttk.Entry(controls, textvariable=self.nickname, width=14).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        self.mode_button = ttk.Button(controls, command=self.toggle_mode)
        self.mode_button.pack(side=tk.LEFT, padx=(0, 8))
        self.direction_button = ttk.Button(controls, command=self.toggle_direction)
        self.direction_button.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(controls, text="Calculate shortest path", command=self.calculate).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(controls, text="Clear all", command=self.clear).pack(side=tk.LEFT)

        self.status = ttk.Label(
            root,
            text="Click the graph to add points. The first point is the start.",
            padding=(12, 0, 12, 8),
        )
        self.status.pack(fill=tk.X)

        self.canvas = tk.Canvas(root, background="#f8fafc", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Configure>", self.draw)
        self.update_mode_button()

    def update_mode_button(self) -> None:
        label = {"points": "Add points", "squares": "Add squares", "circles": "Add circles"}[self.mode]
        self.mode_button.configure(text=f"Mode: {label}")
        self.direction_button.configure(
            text=f"Flow: {'clockwise' if self.next_circle_clockwise else 'counterclockwise'}"
        )

    def toggle_mode(self) -> None:
        self.mode = {"points": "squares", "squares": "circles", "circles": "points"}[self.mode]
        self.drag_start = None
        self.drag_square = None
        self.drag_circle = None
        self.update_mode_button()
        if self.mode == "points":
            self.status.configure(text="Click the graph to add points. The first point is the start.")
        elif self.mode == "squares":
            self.status.configure(text="Click and drag on the graph to draw a square obstacle.")
        else:
            self.status.configure(
                text="Drag from a center to set radius; arrows show flow and routes exit radially."
            )
        self.draw()

    def toggle_direction(self) -> None:
        self.next_circle_clockwise = not self.next_circle_clockwise
        self.update_mode_button()
        self.status.configure(
            text=f"New circles will flow {'clockwise' if self.next_circle_clockwise else 'counterclockwise'}."
        )

    def plot_bounds(self) -> tuple[float, float, float]:
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        size = max(1.0, min(width - 88, height - 72))
        left = (width - size) / 2 + 28
        top = (height - size) / 2 + 8
        return left, top, size

    def to_canvas(self, point: Point) -> tuple[float, float]:
        left, top, size = self.plot_bounds()
        x = left + (point[0] + COORDINATE_LIMIT) / (2 * COORDINATE_LIMIT) * size
        y = top + (COORDINATE_LIMIT - point[1]) / (2 * COORDINATE_LIMIT) * size
        return x, y

    def to_graph(self, x: float, y: float) -> Point | None:
        left, top, size = self.plot_bounds()
        if not (left <= x <= left + size and top <= y <= top + size):
            return None
        graph_x = (x - left) / size * (2 * COORDINATE_LIMIT) - COORDINATE_LIMIT
        graph_y = COORDINATE_LIMIT - (y - top) / size * (2 * COORDINATE_LIMIT)
        return round(graph_x, 1), round(graph_y, 1)

    def on_press(self, event: tk.Event) -> None:
        point = self.to_graph(event.x, event.y)
        if point is None:
            return
        if self.mode == "points":
            point_index = self.point_at_canvas_position(event.x, event.y)
            if point_index is not None:
                self.rename_point(point_index)
            else:
                self.add_point(point)
        elif self.mode == "squares":
            self.drag_start = point
            self.drag_square = None
        else:
            self.drag_start = point
            self.drag_circle = None

    def point_at_canvas_position(self, x: float, y: float) -> int | None:
        nearest: tuple[float, int] | None = None
        for index, point in enumerate(self.points):
            point_x, point_y = self.to_canvas(point)
            distance = math.hypot(x - point_x, y - point_y)
            if distance <= 12 and (nearest is None or distance < nearest[0]):
                nearest = distance, index
        return nearest[1] if nearest is not None else None

    def rename_point(self, index: int) -> None:
        name = simpledialog.askstring(
            "Name point",
            f"Enter a nickname for point {index + 1} (leave blank to remove it):",
            initialvalue=self.point_names[index],
            parent=self.root,
        )
        if name is None:
            return
        self.point_names[index] = name.strip()
        self.clear_tour()
        self.status.configure(
            text=f"Updated point {index + 1}"
            + (f' nickname to "{self.point_names[index]}".' if self.point_names[index] else " nickname.")
        )
        self.draw()

    def on_drag(self, event: tk.Event) -> None:
        if self.drag_start is None or self.mode == "points":
            return
        point = self.to_graph(event.x, event.y)
        if self.mode == "squares":
            self.drag_square = self.square_from_drag(self.drag_start, point) if point is not None else None
        else:
            self.drag_circle = (
                self.circle_from_drag(self.drag_start, point, self.next_circle_clockwise)
                if point is not None
                else None
            )
        self.draw()

    def on_release(self, event: tk.Event) -> None:
        if self.mode == "points" or self.drag_start is None:
            return
        point = self.to_graph(event.x, event.y)
        if self.mode == "squares":
            square = self.square_from_drag(self.drag_start, point) if point is not None else None
            self.drag_start = None
            self.drag_square = None
            if square is None:
                self.status.configure(text="Square cancelled. Drag a larger square fully inside the graph.")
                self.draw()
                return
            if any(
                square[0] < existing[2]
                and existing[0] < square[2]
                and square[1] < existing[3]
                and existing[1] < square[3]
                for existing in self.squares
            ):
                self.status.configure(text="Squares cannot overlap.")
                self.draw()
                return
            if any(
                square[0] < x < square[2] and square[1] < y < square[3]
                for x, y in self.points
            ):
                self.status.configure(text="A square cannot cover an existing point.")
                self.draw()
                return
            if any(self.circle_intersects_square(circle, square) for circle in self.circles):
                self.status.configure(text="Squares cannot overlap a circle.")
                self.draw()
                return
            self.squares.append(square)
            self.clear_tour()
            self.status.configure(text=f"Added square obstacle #{len(self.squares)}.")
            self.draw()
            return

        circle = self.circle_from_drag(self.drag_start, point, self.next_circle_clockwise) if point else None
        self.drag_start = None
        self.drag_circle = None
        if circle is None:
            self.status.configure(text="Circle cancelled. Drag a larger circle fully inside the graph.")
            self.draw()
            return
        center_x, center_y, radius = circle[:3]
        if any(math.dist((center_x, center_y), existing[:2]) < radius + existing[2] for existing in self.circles):
            self.status.configure(text="Circles cannot overlap.")
            self.draw()
            return
        if any(
            math.dist((center_x, center_y), (x, y)) < radius
            for x, y in self.points
        ):
            self.status.configure(text="A circle cannot cover an existing point.")
            self.draw()
            return
        if any(self.circle_intersects_square(circle, square) for square in self.squares):
            self.status.configure(text="Circles cannot overlap a square obstacle.")
            self.draw()
            return
        self.circles.append(circle)
        self.clear_tour()
        self.status.configure(
            text=f"Added circle #{len(self.circles)} flowing "
            f"{'clockwise' if circle[3] else 'counterclockwise'}."
        )
        self.draw()

    @staticmethod
    def circle_from_drag(start: Point, end: Point | None, clockwise: bool) -> Circle | None:
        if end is None:
            return None
        radius = math.dist(start, end)
        if radius < 3:
            return None
        if any(abs(value) > COORDINATE_LIMIT for value in (start[0] - radius, start[0] + radius, start[1] - radius, start[1] + radius)):
            return None
        return start[0], start[1], radius, clockwise

    @staticmethod
    def circle_intersects_square(circle: Circle, square: Square) -> bool:
        center_x, center_y, radius = circle[:3]
        closest_x = max(square[0], min(center_x, square[2]))
        closest_y = max(square[1], min(center_y, square[3]))
        return math.hypot(center_x - closest_x, center_y - closest_y) < radius

    @staticmethod
    def square_from_drag(start: Point, end: Point | None) -> Square | None:
        if end is None:
            return None
        delta_x, delta_y = end[0] - start[0], end[1] - start[1]
        side = max(abs(delta_x), abs(delta_y))
        if side < 3:
            return None
        end_x = start[0] + math.copysign(side, delta_x or 1)
        end_y = start[1] + math.copysign(side, delta_y or 1)
        square = min(start[0], end_x), min(start[1], end_y), max(start[0], end_x), max(start[1], end_y)
        if any(abs(value) > COORDINATE_LIMIT for value in square):
            return None
        return square

    def add_point(self, point: Point) -> None:
        if len(self.points) >= MAX_POINTS:
            messagebox.showwarning(
                "Point limit reached",
                f"Exact shortest-path calculation is limited to {MAX_POINTS} points.",
                parent=self.root,
            )
            return
        if any(math.dist(point, existing) < 3 for existing in self.points):
            self.status.configure(text="That point is too close to an existing point.")
            return
        if any(x_min < point[0] < x_max and y_min < point[1] < y_max for x_min, y_min, x_max, y_max in self.squares):
            self.status.configure(text="Points cannot be placed inside a square obstacle.")
            return
        if any(math.dist(point, circle[:2]) < circle[2] for circle in self.circles):
            self.status.configure(text="Points cannot be placed inside a circle flow.")
            return

        name = self.nickname.get().strip()
        self.points.append(point)
        self.point_names.append(name)
        self.nickname.set("")
        self.clear_tour()
        self.status.configure(
            text=f"Added point {len(self.points)}"
            + (f' "{name}"' if name else "")
            + f" at ({point[0]:.1f}, {point[1]:.1f}). "
            "The first point is the start."
        )
        self.draw()

    def clear_tour(self) -> None:
        self.tour = None
        self.total_distance = None

    def calculate(self) -> None:
        if not self.points:
            messagebox.showinfo("No points", "Click the graph to add at least one point.", parent=self.root)
            return

        try:
            self.tour, self.total_distance = obstacle_aware_tour(
                self.points, self.squares, self.circles
            )
        except ValueError as error:
            messagebox.showerror("No valid route", str(error), parent=self.root)
            return
        self.status.configure(
            text=f"Shortest round trip: {self.total_distance:.2f} units "
            f"({len(self.points)} points; returns to point 1)."
        )
        self.draw()

    def clear(self) -> None:
        self.points.clear()
        self.point_names.clear()
        self.squares.clear()
        self.circles.clear()
        self.clear_tour()
        self.status.configure(text="Graph cleared. Click to add points or switch drawing mode.")
        self.draw()

    def draw(self, event: tk.Event | None = None) -> None:
        if event is not None and event.widget is not self.canvas:
            return
        self.canvas.delete("all")
        left, top, size = self.plot_bounds()
        right = left + size
        bottom = top + size

        for value in range(-COORDINATE_LIMIT, COORDINATE_LIMIT + 1, GRID_STEP):
            x = left + (value + COORDINATE_LIMIT) / (2 * COORDINATE_LIMIT) * size
            y = top + (COORDINATE_LIMIT - value) / (2 * COORDINATE_LIMIT) * size
            axis_color = "#64748b" if value == 0 else "#dbe3ed"
            axis_width = 2 if value == 0 else 1
            self.canvas.create_line(x, top, x, bottom, fill=axis_color, width=axis_width)
            self.canvas.create_line(left, y, right, y, fill=axis_color, width=axis_width)
            self.canvas.create_text(x, bottom + 16, text=str(value), fill="#475569", font=("Segoe UI", 8))
            self.canvas.create_text(left - 18, y, text=str(value), fill="#475569", font=("Segoe UI", 8))

        self.canvas.create_rectangle(left, top, right, bottom, outline="#64748b")
        self.canvas.create_text(right, bottom + 36, text="x", fill="#334155", font=("Segoe UI", 10, "bold"))
        self.canvas.create_text(
            left - 38, top, text="y", fill="#334155", font=("Segoe UI", 10, "bold")
        )

        for square in (*self.squares, *((self.drag_square,) if self.drag_square else ())):
            x1, y1 = self.to_canvas((square[0], square[3]))
            x2, y2 = self.to_canvas((square[2], square[1]))
            self.canvas.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                fill="#fca5a5",
                stipple="gray25",
                outline="#dc2626",
                width=2,
            )

        for circle in (*self.circles, *((self.drag_circle,) if self.drag_circle else ())):
            center_x, center_y, radius, clockwise = circle
            center_canvas_x, center_canvas_y = self.to_canvas((center_x, center_y))
            pixel_radius = radius / (2 * COORDINATE_LIMIT) * size
            self.canvas.create_oval(
                center_canvas_x - pixel_radius,
                center_canvas_y - pixel_radius,
                center_canvas_x + pixel_radius,
                center_canvas_y + pixel_radius,
                fill="#ddd6fe",
                stipple="gray25",
                outline="#7c3aed",
                width=2,
            )
            for angle in (math.pi / 4, 5 * math.pi / 4):
                start_angle = angle + (0.18 if clockwise else -0.18)
                end_angle = angle - (0.18 if clockwise else -0.18)
                arrow_start = self.to_canvas(
                    (center_x + radius * math.cos(start_angle), center_y + radius * math.sin(start_angle))
                )
                arrow_end = self.to_canvas(
                    (center_x + radius * math.cos(end_angle), center_y + radius * math.sin(end_angle))
                )
                self.canvas.create_line(
                    *arrow_start,
                    *arrow_end,
                    fill="#6d28d9",
                    width=2,
                    arrow=tk.LAST,
                    arrowshape=(8, 10, 4),
                )

        if self.tour is not None:
            for start, end in zip(self.tour, self.tour[1:]):
                matching_circle = next(
                    (
                        circle
                        for circle in self.circles
                        if math.isclose(math.dist(start, circle[:2]), circle[2], abs_tol=1e-6)
                        and math.isclose(math.dist(end, circle[:2]), circle[2], abs_tol=1e-6)
                    ),
                    None,
                )
                if matching_circle is not None:
                    center_x, center_y, radius, clockwise = matching_circle
                    center_canvas_x, center_canvas_y = self.to_canvas((center_x, center_y))
                    pixel_radius = radius / (2 * COORDINATE_LIMIT) * size
                    start_angle = math.degrees(math.atan2(start[1] - center_y, start[0] - center_x))
                    end_angle = math.degrees(math.atan2(end[1] - center_y, end[0] - center_x))
                    extent = (start_angle - end_angle) % 360 if clockwise else (end_angle - start_angle) % 360
                    self.canvas.create_arc(
                        center_canvas_x - pixel_radius,
                        center_canvas_y - pixel_radius,
                        center_canvas_x + pixel_radius,
                        center_canvas_y + pixel_radius,
                        start=start_angle,
                        extent=-extent if clockwise else extent,
                        style=tk.ARC,
                        outline="#e11d48",
                        width=3,
                    )
                else:
                    x1, y1 = self.to_canvas(start)
                    x2, y2 = self.to_canvas(end)
                    self.canvas.create_line(
                        x1,
                        y1,
                        x2,
                        y2,
                        fill="#e11d48",
                        width=3,
                        arrow=tk.LAST,
                        arrowshape=(10, 12, 5),
                    )
        else:
            for first in range(len(self.points)):
                for second in range(first + 1, len(self.points)):
                    if any(
                        segment_crosses_square(self.points[first], self.points[second], square)
                        for square in self.squares
                    ):
                        continue
                    x1, y1 = self.to_canvas(self.points[first])
                    x2, y2 = self.to_canvas(self.points[second])
                    self.canvas.create_line(x1, y1, x2, y2, fill="#cbd5e1", width=1)

        for index, point in enumerate(self.points):
            x, y = self.to_canvas(point)
            color = "#16a34a" if index == 0 else "#2563eb"
            self.canvas.create_oval(x - 7, y - 7, x + 7, y + 7, fill=color, outline="white", width=2)
            self.canvas.create_text(
                x + 11,
                y - 11,
                text=f"{index + 1}: {self.point_names[index]}"
                if self.point_names[index]
                else str(index + 1),
                anchor=tk.SW,
                fill="#0f172a",
                font=("Segoe UI", 9, "bold"),
            )


def main() -> None:
    root = tk.Tk()
    ShortestPathGraph(root)
    root.mainloop()


if __name__ == "__main__":
    main()
