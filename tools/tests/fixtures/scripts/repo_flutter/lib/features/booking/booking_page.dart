import 'package:flutter/material.dart';

class BookingPage extends StatefulWidget {
  @override
  State<BookingPage> createState() => _BookingPageState();
}

class _BookingPageState extends State<BookingPage> {
  @override
  Widget build(BuildContext context) {
    return Form(
      child: Column(children: [
        TextFormField(decoration: const InputDecoration(labelText: 'Имя')),
        TextFormField(decoration: const InputDecoration(labelText: 'Телефон')),
        CheckboxListTile(
          value: true,
          onChanged: (v) {},
          title: const Text('Я согласен на обработку персональных данных'),
        ),
      ]),
    );
  }
}
