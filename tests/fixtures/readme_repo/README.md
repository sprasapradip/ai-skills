# invoice-kit

Invoice-kit generates tax-ready PDF invoices from Laravel models, with multi-currency totals and Nepali VAT rules built in.

## Table of Contents

<!-- toc -->
<!-- tocstop -->

## Features

- Multi-currency totals with exact decimal math
- Nepal VAT (13%) and custom tax rules

## Installation

```bash
composer require acme/invoice-kit
```

## Usage

```php
$pdf = Invoice::for($order)->render();
```

See the [full guide](docs/guide.md) and [installation notes](#installation).

## Contributing

Open an issue before large changes.

## License

MIT
