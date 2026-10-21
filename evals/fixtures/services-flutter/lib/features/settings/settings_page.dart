import 'package:flutter/material.dart';

class SettingsPage extends StatelessWidget {
  const SettingsPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Настройки')),
      body: ListView(
        children: const [
          ListTile(title: Text('Уведомления о записи')),
          ListTile(title: Text('Версия 1.0.3')),
        ],
      ),
    );
  }
}
