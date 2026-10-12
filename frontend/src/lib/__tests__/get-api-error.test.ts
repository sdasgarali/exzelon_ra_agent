import { getApiError } from '../api'

const err = (detail: any) => ({ response: { data: { detail } } })

describe('getApiError', () => {
  test('returns the fallback when there is no detail', () => {
    expect(getApiError({}, 'fallback')).toBe('fallback')
    expect(getApiError(undefined, 'fallback')).toBe('fallback')
  })

  test('passes string details through', () => {
    expect(getApiError(err('Nope'))).toBe('Nope')
  })

  test('flattens a pydantic 422 list into readable text', () => {
    const msg = getApiError(err([
      { type: 'value_error', loc: ['body', 'password'], msg: 'Value error, Password must contain at least one uppercase letter' },
      { type: 'missing', loc: ['body', 'full_name'], msg: 'Field required' },
    ]))
    expect(msg).toBe('Password must contain at least one uppercase letter; Full name: Field required')
  })

  test('de-duplicates repeated messages and never returns JSON', () => {
    const msg = getApiError(err([
      { type: 'missing', loc: ['body', 'email'], msg: 'Field required' },
      { type: 'missing', loc: ['body', 'email'], msg: 'Field required' },
      { weird: true },
    ]), 'fb')
    expect(msg).toBe('Email: Field required')
  })

  test('object details use message/msg, else the fallback', () => {
    expect(getApiError(err({ message: 'Payments unavailable', code: 'x' }))).toBe('Payments unavailable')
    expect(getApiError(err({ msg: 'Bad thing' }))).toBe('Bad thing')
    expect(getApiError(err({ code: 'x' }), 'fb')).toBe('fb')
  })
})
