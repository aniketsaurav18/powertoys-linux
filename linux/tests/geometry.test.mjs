// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {rectangle, zone} from '../gnome-extension/powertoys-linux@local/geometry.js';

test('zones fit logical work areas with negative monitor origins', () => {
    const area = {x: -1600, y: 24, width: 1600, height: 876};
    assert.deepEqual(zone(area, 2, 1, 0, 8), {x: -1592, y: 32, width: 784, height: 860});
    assert.deepEqual(zone(area, 2, 1, 1, 8), {x: -792, y: 32, width: 784, height: 860});
    assert.throws(() => zone(area, 2, 1, 2));
    assert.throws(() => rectangle(0, 0, 100, 100, area));
});

test('all grid zones remain in their monitor and do not overlap', () => {
    for (let columns = 1; columns <= 6; columns++) {
        for (let rows = 1; rows <= 6; rows++) {
            const area = {x: -1200, y: -800, width: 1921, height: 1081};
            const zones = Array.from({length: columns * rows}, (_, i) => zone(area, columns, rows, i));
            for (let i = 0; i < zones.length; i++) {
                const a = zones[i];
                assert.ok(a.x >= area.x && a.y >= area.y);
                assert.ok(a.x + a.width <= area.x + area.width);
                assert.ok(a.y + a.height <= area.y + area.height);
                for (let j = i + 1; j < zones.length; j++) {
                    const b = zones[j];
                    assert.ok(a.x + a.width <= b.x || b.x + b.width <= a.x || a.y + a.height <= b.y || b.y + b.height <= a.y);
                }
            }
        }
    }
});

test('bounded fuzz inputs reject invalid grid and rectangle values', () => {
    const area = {x: 0, y: 0, width: 1600, height: 900};
    let seed = 732;
    const next = () => {seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed;};
    for (let i = 0; i < 1000; i++) {
        const columns = next() % 16 - 4, rows = next() % 16 - 4, index = next() % 80 - 10;
        if (columns >= 1 && columns <= 6 && rows >= 1 && rows <= 6 && index >= 0 && index < columns * rows)
            assert.ok(zone(area, columns, rows, index).width >= 64);
        else
            assert.throws(() => zone(area, columns, rows, index));
    }
});
