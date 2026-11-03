package com.acme.bank.service;

import com.acme.bank.model.Account;
import com.acme.bank.model.Transaction;
import com.acme.bank.repository.AccountRepository;
import com.acme.bank.repository.TransactionRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
public class TransferService {

    @Autowired
    private AccountRepository accounts;

    @Autowired
    private TransactionRepository transactions;

    public void transfer(Long fromId, Long toId, double amount) {
        Account from = accounts.findById(fromId).orElseThrow();
        Account to = accounts.findById(toId).orElseThrow();
        if (from.getBalance() < amount) {
            throw new IllegalStateException("Insufficient funds");
        }
        from.setBalance(from.getBalance() - amount);
        accounts.save(from);
        transactions.save(new Transaction(from, -amount));
        to.setBalance(to.getBalance() + amount);
        accounts.save(to);
        transactions.save(new Transaction(to, amount));
    }

    public Map<Long, Double> monthlyTotals() {
        Map<Long, Double> totals = new HashMap<>();
        List<Account> all = accounts.findAll();
        for (Account a : all) {
            double sum = 0;
            for (Transaction t : a.getTransactions()) {
                sum += t.getAmount();
            }
            totals.put(a.getId(), sum);
        }
        return totals;
    }

    @Transactional
    private void audit(Account account) {
        System.out.println("Audit: " + account.getId() + " " + account.getIban() + " " + account.getBalance());
    }
}
