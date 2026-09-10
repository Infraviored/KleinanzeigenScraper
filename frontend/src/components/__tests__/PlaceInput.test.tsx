import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import PlaceInput, { type Place } from '../PlaceInput';

const mockPlaces: Place[] = [
  {
    label: 'Landsberg am Lech (86899, Bayern)',
    name: 'Landsberg am Lech',
    qualifier: '',
    state: 'Bayern',
    postal_code: '86899',
    lat: 48.05,
    lon: 10.87,
  },
  {
    label: 'Landsberg (06188, Sachsen-Anhalt)',
    name: 'Landsberg',
    qualifier: '',
    state: 'Sachsen-Anhalt',
    postal_code: '06188',
    lat: 51.52,
    lon: 12.16,
  },
];

describe('PlaceInput', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders input with label and placeholder', () => {
    render(
      <PlaceInput
        label="Origin"
        placeholder="Start typing town..."
        value={null}
        onChange={vi.fn()}
        emptyHint="No matches found"
      />
    );

    expect(screen.getByLabelText('Origin')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Start typing town...')).toBeInTheDocument();
  });

  it('debounces place suggestions and displays returned matches', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ places: mockPlaces }),
    });
    globalThis.fetch = fetchMock;

    render(
      <PlaceInput
        label="Origin"
        placeholder="Search place..."
        value={null}
        onChange={vi.fn()}
        emptyHint="No places found"
      />
    );

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'La' } });

    // Does not immediately call fetch before debounce delay
    expect(fetchMock).not.toHaveBeenCalled();

    // After debounce delay, fetch is called with query
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/places/suggest?q=La');
    });

    // Both place options appear in listbox
    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument();
    });

    expect(screen.getByText('Landsberg am Lech')).toBeInTheDocument();
    expect(screen.getByText('Landsberg')).toBeInTheDocument();
    expect(screen.getByText('86899')).toBeInTheDocument();
    expect(screen.getByText('06188')).toBeInTheDocument();
  });

  it('does not trigger lookup when input has fewer than 2 characters', async () => {
    const fetchMock = vi.fn();
    globalThis.fetch = fetchMock;

    render(
      <PlaceInput
        label="Origin"
        placeholder="Search..."
        value={null}
        onChange={vi.fn()}
        emptyHint="No matches"
      />
    );

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'L' } });

    // Wait past debounce threshold
    await new Promise(r => setTimeout(r, 220));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('selects suggestion on click and suppresses secondary lookup via skipNextLookup', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ places: mockPlaces }),
    });
    globalThis.fetch = fetchMock;

    const onChange = vi.fn();
    render(
      <PlaceInput
        label="Origin"
        placeholder="Search..."
        value={null}
        onChange={onChange}
        emptyHint="No matches"
      />
    );

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'Lands' } });

    await waitFor(() => {
      expect(screen.getByText('Landsberg am Lech')).toBeInTheDocument();
    });

    // Click the first suggestion
    const firstOption = screen.getAllByRole('option')[0];
    fireEvent.mouseDown(firstOption);

    // onChange was triggered with the selected Place
    expect(onChange).toHaveBeenCalledWith(mockPlaces[0]);

    // Input text was updated to place label
    expect(input).toHaveValue(mockPlaces[0].label);

    // Dropdown is closed
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();

    // Reset fetch mock count and wait past debounce time
    fetchMock.mockClear();
    await new Promise(r => setTimeout(r, 250));

    // skipNextLookup ensured setting the input text did not trigger another suggestion fetch
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('supports keyboard navigation: arrow keys cycle active selection and Enter selects', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ places: mockPlaces }),
    });
    globalThis.fetch = fetchMock;

    const onChange = vi.fn();
    render(
      <PlaceInput
        label="Origin"
        placeholder="Search..."
        value={null}
        onChange={onChange}
        emptyHint="No matches"
      />
    );

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'Lands' } });

    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument();
    });

    const options = screen.getAllByRole('option');
    expect(options[0]).toHaveAttribute('aria-selected', 'true');
    expect(options[1]).toHaveAttribute('aria-selected', 'false');

    // Arrow down moves selection to 2nd option
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(options[0]).toHaveAttribute('aria-selected', 'false');
    expect(options[1]).toHaveAttribute('aria-selected', 'true');

    // Arrow down wraps back to 1st option
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(options[0]).toHaveAttribute('aria-selected', 'true');

    // Arrow up wraps backwards to 2nd option
    fireEvent.keyDown(input, { key: 'ArrowUp' });
    expect(options[1]).toHaveAttribute('aria-selected', 'true');

    // Press Enter to select the 2nd option
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onChange).toHaveBeenCalledWith(mockPlaces[1]);
    expect(input).toHaveValue(mockPlaces[1].label);
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('closes dropdown on Escape and Tab without selecting', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ places: mockPlaces }),
    });
    globalThis.fetch = fetchMock;

    const onChange = vi.fn();
    render(
      <PlaceInput
        label="Origin"
        placeholder="Search..."
        value={null}
        onChange={onChange}
        emptyHint="No matches"
      />
    );

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'Lands' } });

    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument();
    });

    // Escape closes dropdown
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();

    // Reopen by focusing with matches still in state
    fireEvent.focus(input);
    expect(screen.getByRole('listbox')).toBeInTheDocument();

    // Tab closes dropdown
    fireEvent.keyDown(input, { key: 'Tab' });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('synchronizes and clears input when value prop is cleared externally', () => {
    const { rerender } = render(
      <PlaceInput
        label="Origin"
        placeholder="Search..."
        value={mockPlaces[0]}
        onChange={vi.fn()}
        emptyHint="No matches"
      />
    );

    const input = screen.getByRole('combobox');
    expect(input).toHaveValue(mockPlaces[0].label);

    // Parent resets value to null (e.g. corridor planned)
    rerender(
      <PlaceInput
        label="Origin"
        placeholder="Search..."
        value={null}
        onChange={vi.fn()}
        emptyHint="No matches"
      />
    );

    expect(input).toHaveValue('');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('calls onChange(null) when user modifies text after selecting a place', async () => {
    const onChange = vi.fn();
    render(
      <PlaceInput
        label="Origin"
        placeholder="Search..."
        value={mockPlaces[0]}
        onChange={onChange}
        emptyHint="No matches"
      />
    );

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'Landsberg am Lech modified' } });

    expect(onChange).toHaveBeenCalledWith(null);
  });
});
