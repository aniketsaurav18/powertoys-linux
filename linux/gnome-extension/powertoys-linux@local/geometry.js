// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

export function rectangle(x, y, width, height, area) {
    if (![x, y, width, height].every(Number.isInteger) ||
        width < 64 || height < 64 || width > area.width || height > area.height ||
        x < area.x || y < area.y || x + width > area.x + area.width ||
        y + height > area.y + area.height)
        throw new Error('Window rectangle must fit inside the selected monitor work area.');
    return {x, y, width, height};
}

export function zone(area, columns, rows, index, gap = 8) {
    if (![columns, rows, index, gap].every(Number.isInteger) ||
        columns < 1 || columns > 6 || rows < 1 || rows > 6 ||
        index < 0 || index >= columns * rows || gap < 0 || gap > 64)
        throw new Error('Invalid zone layout.');
    const column = index % columns;
    const row = Math.floor(index / columns);
    const left = area.x + Math.round(column * area.width / columns) + gap;
    const top = area.y + Math.round(row * area.height / rows) + gap;
    const right = area.x + Math.round((column + 1) * area.width / columns) - gap;
    const bottom = area.y + Math.round((row + 1) * area.height / rows) - gap;
    return rectangle(left, top, right - left, bottom - top, area);
}
