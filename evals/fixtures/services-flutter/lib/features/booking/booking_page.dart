import 'package:appmetrica_plugin/appmetrica_plugin.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

const prepaymentPercent = 30;
const servicePriceRub = 3000;

class BookingPage extends StatefulWidget {
  const BookingPage({super.key});

  @override
  State<BookingPage> createState() => _BookingPageState();
}

class _BookingPageState extends State<BookingPage> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _phone = TextEditingController();
  final _comment = TextEditingController();

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    // Creates the booking and opens the YooKassa payment sheet for the prepayment.
    final prepayment = servicePriceRub * prepaymentPercent ~/ 100;
    AppMetrica.reportEvent('booking_started');
    // payment sheet call omitted in the fixture: amount = $prepayment RUB
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Запись на приём')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          child: Column(
            children: [
              TextFormField(controller: _name, decoration: const InputDecoration(labelText: 'Имя')),
              TextFormField(controller: _phone, decoration: const InputDecoration(labelText: 'Телефон')),
              TextFormField(controller: _comment, decoration: const InputDecoration(labelText: 'Комментарий')),
              const SizedBox(height: 16),
              Text('Предоплата $prepaymentPercent% стоимости услуги, остальное — на месте.'),
              ElevatedButton(onPressed: _submit, child: const Text('Записаться и оплатить')),
              TextButton(onPressed: () => context.go('/reviews'), child: const Text('Отзывы')),
              TextButton(onPressed: () => context.go('/settings'), child: const Text('Настройки')),
            ],
          ),
        ),
      ),
    );
  }
}
